"""Enrichment pipeline: takes lots.jsonl from a scraper and adds
  1. EPC match          → UPRN, floor area, age band (free API, register for a key)
  2. Prior sales        → Land Registry PPD lookup for the exact property
  3. Neighbourhood comps→ HPI-adjusted median for same sector + type
  4. Condition class    → keyword classifier over the lot description (free, no LLM)
  5. Re-offer count     → how often this property_key appeared in earlier auctions

Env (.env):
  EPC_EMAIL=you@example.com
  EPC_KEY=xxxx                      # from https://epc.opendatacommunities.org/
  DATABASE_URL=postgres://...       # your Supabase connection string
  HPI_AREA_CODE=K02000001           # optional; default is UK-wide

PPD loading (once, then monthly):
  Download CSV from gov.uk "Price Paid Data downloads", then:
  python enrich.py --load-ppd pp-2025.csv

Dry run without a database (condition classifier only):
  python enrich.py --lots lots.jsonl --no-db
"""

import argparse
import base64
import csv
import json
import os
import re
import statistics
import sys

import requests

from common import house_number

try:
    import psycopg2
    from psycopg2.extras import execute_batch
except ImportError:
    psycopg2 = None

# RETIRED. The Open Data Communities EPC API was switched off on 30 May 2026;
# this host now 301s to get-energy-performance-data.communities.gov.uk, so every
# request returns the new service's HTML landing page with a 200 status. The old
# code read that as "no rows" and silently returned None for every lot, which is
# worse than failing. epc_lookup() now says so instead of pretending to work.
# Replacement route is a bulk download behind GOV.UK One Login — see src/epc_load.py.
EPC_URL = "https://epc.opendatacommunities.org/api/v1/domestic/search"
EPC_RETIRED_NOTE = (
    "The EPC search API was retired on 30 May 2026 and now redirects to "
    "get-energy-performance-data.communities.gov.uk, which requires GOV.UK One "
    "Login and serves bulk downloads only. Download the domestic certificates "
    "file from that service and use src/epc_load.py instead."
)
# UK-wide HPI series. The hpi table holds one row per (area_code, month), so a
# lookup by month alone silently picks whichever region happens to sort first.
DEFAULT_HPI_AREA = "K02000001"

# ---------------------------------------------------------------- condition ---
# Regex ruleset tuned to UK auction copy, built from real SDL listing text.
# Order matters: worst class wins.
#
# These are patterns rather than plain substrings because auction copy varies the
# verb form and slips qualifiers between the verb and the noun. A substring list
# containing "requires modernisation" matches none of these real examples:
#   "requires general modernisation throughout"
#   "in need of full modernisation and upgrading"
#   "requiring a scheme of improvement and upgrading"
#   "requiring refurbishment"
#   "in need of a scheme of updating and modernisation"
# On a 60-lot sample the substring version classified 48 as 'unknown'.

_VERB = r"(?:requir(?:es?|ing|ed)|in need of|needs?|would benefit from|benefit(?:s|ting) from)"
_SCHEME = r"(?:\s+an?)?(?:\s+scheme\s+of)?"
_HEAVY_Q = r"(?:general|full|complete|total|extensive|substantial|significant|comprehensive|major)"
_LIGHT_Q = r"(?:some|light|minor|cosmetic|slight|a little)"
_WORK = (r"(?:modernisation|modernization|renovation|refurbishment|refurbishing|"
         r"updating|upgrading|improvement|improving|repairs?|works)")
# Deliberately NOT in _WORK: "potential" and "development". In auction headings
# "WITH POTENTIAL" means development potential — it appears on land, former
# churches and care homes — and says nothing about the building's condition.
# Up to two filler words ("and", "internal", …) between the qualifier and the noun.
_GAP = r"(?:\s+\w+){0,2}?\s+"

CONDITION_RULES = [
    ("structural", [
        r"structural movement", r"subsidence", r"underpin", r"fire[- ]damage",
        r"fire[- ]damaged", r"flood damage", r"derelict", r"\bshell\b", r"unsafe",
        r"partially demolished", r"japanese knotweed", r"structural repair",
        r"dangerous structure",
    ]),
    ("full_refurb", [
        rf"{_VERB}{_SCHEME}\s+(?:{_HEAVY_Q}{_GAP})?{_WORK}",
        # Auction HEADINGS are terse and drop the verb entirely:
        #   "MID-TERRACE HOUSE FOR REFURBISHMENT", "HOUSE FOR IMPROVEMENT"
        # That idiom covers ~250 lots in one house's catalogue that the
        # sentence-shaped rules above never match.
        rf"\bfor\s+(?:{_HEAVY_Q}\s+)?{_WORK}\b",
        r"uninhabitable", r"back to brick", r"renovation project", r"doer[- ]upper",
        r"full refurbishment", r"complete refurbishment",
    ]),
    ("light_refurb", [
        rf"{_VERB}{_SCHEME}\s+{_LIGHT_Q}{_GAP}{_WORK}",
        r"\bcosmetic\b", r"decorative order",
    ]),
    ("ready", [
        r"\bwell[- ]presented\b", r"\bimmaculate\b", r"walk[- ]in condition",
        r"ready to let", r"no work required", r"modernised throughout",
        r"(?:recently|newly) (?:refurbished|renovated|modernised)",
        r"in (?:excellent|exceptional|first[- ]class) (?:decorative )?(?:order|condition)",
    ]),
]
CONDITION_RULES = [(cls, [re.compile(p, re.I) for p in pats])
                   for cls, pats in CONDITION_RULES]

# Auction copy sells the neighbourhood as hard as the building, so a cue word is
# only trusted when it is describing the lot itself.
#   "close to the newly refurbished Buxton Crescent Spa"  -> not a refurbished lot
#   "timber shed and part derelict brick coal stores"     -> not a derelict house
_PROXIMITY_BEFORE = re.compile(
    r"(?:close to|next to|opposite|adjacent to|near(?:by|est| to)?|"
    r"walking distance (?:of|to)|within (?:easy )?(?:reach|walking))\b[^.]{0,45}$", re.I)
_OUTBUILDING_AFTER = re.compile(
    r"\b(?:coal store|outbuilding|out[- ]?house|shed|garage|stable|barn|store|"
    r"workshop|annexe?)s?\b", re.I)
_CLASS_VETO = {
    "structural": (None, _OUTBUILDING_AFTER),
    "ready": (_PROXIMITY_BEFORE, None),
}


def _fires(pattern, text: str, before_veto, after_veto) -> bool:
    """True if the pattern matches somewhere its surrounding context doesn't veto."""
    for m in pattern.finditer(text):
        if before_veto and before_veto.search(text[max(0, m.start() - 70):m.start()]):
            continue
        if after_veto and after_veto.search(text[m.start():m.end() + 45]):
            continue
        return True
    return False
FLAG_TERMS = {
    "tenanted": ["tenanted", "assured shorthold", "sitting tenant", "regulated tenancy",
                 "currently let", "subject to tenancy"],
    "vacant": ["vacant possession", "vacant"],
    "short_lease": ["short lease", "lease of approximately"],
    "hmo": ["hmo", "house in multiple occupation"],
    "commercial_element": ["mixed use", "mixed-use", "retail unit", "commercial"],
    "land_only": ["building plot", "land only", "parcel of land", "development site"],
}


def classify_condition(description: str) -> tuple[str, list[str]]:
    text = (description or "").lower()
    flags = [flag for flag, terms in FLAG_TERMS.items() if any(t in text for t in terms)]
    for cls, patterns in CONDITION_RULES:
        before_veto, after_veto = _CLASS_VETO.get(cls, (None, None))
        if any(_fires(p, text, before_veto, after_veto) for p in patterns):
            return cls, flags
    return "unknown", flags


# ---------------------------------------------------------------------- EPC ---
def epc_lookup(postcode: str, address: str,
               session: requests.Session | None = None) -> dict | None:
    """Best EPC match for a postcode + house number. Free API; Basic auth."""
    email, key = os.environ.get("EPC_EMAIL"), os.environ.get("EPC_KEY")
    if not (email and key and postcode):
        return None
    token = base64.b64encode(f"{email}:{key}".encode()).decode()
    get = (session or requests).get
    try:
        r = get(
            EPC_URL,
            params={"postcode": postcode, "size": 100},
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"  ! EPC {postcode}: {e}", file=sys.stderr)
        return None
    if r.status_code != 200 or not r.text.strip():
        return None
    if "json" not in (r.headers.get("content-type") or ""):
        # The retired endpoint answers 200 with HTML. Do not treat that as "no
        # certificate found" — it would quietly blank the EPC columns corpus-wide.
        raise RuntimeError(EPC_RETIRED_NOTE)
    try:
        rows = r.json().get("rows", [])
    except ValueError:
        return None

    houseno = house_number(address)
    best, confidence = None, "none"
    for row in rows:
        addr = " ".join(str(row.get(k, "")) for k in ("address1", "address2", "address3")).lower()
        if houseno and re.search(rf"\b{re.escape(houseno)}\b", addr):
            best, confidence = row, "exact"
            break
    if best is None and len(rows) == 1:
        best, confidence = rows[0], "fuzzy"
    if best is None:
        return None
    return {
        "uprn": best.get("uprn"),
        "floor_area_m2": _num(best.get("total-floor-area")),
        "construction_age_band": best.get("construction-age-band"),
        "epc_rating": best.get("current-energy-rating"),
        "epc_property_type": best.get("property-type"),
        "match_confidence": confidence,
    }


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------- PPD ---
# Official column order: id, price, date, postcode, type, new, tenure,
# paon, saon, street, locality, town, district, county, category, status
PPD_INSERT = """insert into ppd (transaction_id, price, transfer_date, postcode,
    property_type, new_build, tenure, paon, saon, street, town)
    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    on conflict (transaction_id) do nothing"""


def load_ppd(conn, csv_path: str, batch: int = 5000) -> None:
    """Load an official Price Paid CSV (no header, fixed column order)."""
    loaded = skipped = 0
    pending: list[tuple] = []
    # encoding matters: the PPD extract is UTF-8 and the Windows default (cp1252)
    # raises UnicodeDecodeError partway through the file.
    with conn.cursor() as cur, open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            try:
                pending.append((
                    row[0].strip("{}"), int(row[1]), row[2][:10], row[3] or None,
                    row[4], row[5] == "Y", row[6], row[7], row[8], row[9], row[11],
                ))
            except (IndexError, ValueError):
                skipped += 1     # malformed line; the extract has a few every year
                continue
            if len(pending) >= batch:
                execute_batch(cur, PPD_INSERT, pending)
                conn.commit()
                loaded += len(pending)
                pending.clear()
                print(f"  {loaded} rows...")
        if pending:
            execute_batch(cur, PPD_INSERT, pending)
            loaded += len(pending)
    conn.commit()
    print(f"Loaded {loaded} rows ({skipped} malformed lines skipped)")


def prior_sales(conn, postcode: str, address: str) -> dict:
    houseno = house_number(address)
    if not (postcode and houseno):
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """select price, transfer_date from ppd
               where postcode = %s and lower(paon) = %s
               order by transfer_date desc limit 1""",
            (postcode, houseno),
        )
        row = cur.fetchone()
    return {"prior_sale_price": row[0], "prior_sale_date": row[1]} if row else {}


def hpi_area_for(conn, postcode: str | None, cache: dict) -> str:
    """The lot's local-authority ONS code, falling back to the national series.

    Without this every lot is adjusted by one index: a Lambeth flat and a Stoke
    terrace move by the same ratio, which defeats the point of adjusting at all.
    """
    if not postcode:
        return DEFAULT_HPI_AREA
    if postcode not in cache:
        with conn.cursor() as cur:
            cur.execute("select admin_district_code from postcode_geo where postcode = %s",
                        (postcode,))
            row = cur.fetchone()
        cache[postcode] = (row[0] if row and row[0] else None)
    return cache[postcode] or DEFAULT_HPI_AREA


def load_hpi_ratios(conn, area_code: str) -> dict:
    """month ('YYYY-MM') -> ratio scaling a sale in that month up to the latest month.

    Loaded once. The original ran this as a correlated subquery per comparable
    sale — one database round trip per row, thousands per run — and, because it
    matched on month alone against a table keyed by (area_code, month), it picked
    an arbitrary region's index value.
    """
    with conn.cursor() as cur:
        cur.execute(
            """select month, index_value from hpi
               where area_code = %s and index_value is not null and index_value <> 0
               order by month""",
            (area_code,),
        )
        rows = cur.fetchall()
    if not rows:
        return {}
    latest = float(rows[-1][1])
    return {m.strftime("%Y-%m"): latest / float(v) for m, v in rows}


def sector_comps(conn, sector: str, property_type: str | None,
                 hpi_ratios: dict, months: int = 24) -> dict:
    """HPI-adjusted median sale price for the postcode sector."""
    empty = {"comp_count": 0, "comp_median_price": None}
    if not sector:
        return empty

    sql = ["""select price, transfer_date from ppd
              where postcode like %s
                and transfer_date > (current_date - make_interval(months => %s))"""]
    params: list = [sector + "%", months]
    if property_type:
        sql.append("and property_type = %s")
        params.append(property_type)

    with conn.cursor() as cur:
        cur.execute(" ".join(sql), params)
        rows = cur.fetchall()

    if not rows:
        return empty
    # A missing HPI month falls back to 1.0 (no adjustment) rather than dropping
    # the sale — a slightly stale comp beats a thinner comp set.
    adjusted = [price * hpi_ratios.get(tdate.strftime("%Y-%m"), 1.0) for price, tdate in rows]
    return {"comp_count": len(adjusted),
            "comp_median_price": int(statistics.median(adjusted))}


# ----------------------------------------------------------------- upserts ---
LOT_UPSERT = """
insert into lots (source, source_lot_id, lot_url, auction_date, first_seen, listed_at,
                  address_raw, postcode, postcode_sector, property_key, guide_price,
                  guide_price_max, hammer_price, status, result_raw, description,
                  property_type, bedrooms)
values (%(source)s,%(source_lot_id)s,%(lot_url)s,%(auction_date)s,
        coalesce(%(first_seen)s, current_date),
        %(listed_at)s,%(address_raw)s,%(postcode)s,%(postcode_sector)s,%(property_key)s,
        %(guide_price)s,%(guide_price_max)s,%(hammer_price)s,%(status)s,%(result_raw)s,
        %(description)s,%(property_type)s,%(bedrooms)s)
on conflict on constraint lots_source_lot_uniq do update set
    lot_url         = excluded.lot_url,
    listed_at       = excluded.listed_at,
    guide_price     = excluded.guide_price,
    guide_price_max = excluded.guide_price_max,
    hammer_price    = excluded.hammer_price,
    status          = excluded.status,
    result_raw      = excluded.result_raw,
    -- keep any existing description if this pass ran without --with-descriptions
    description     = coalesce(nullif(excluded.description, ''), lots.description),
    property_type   = coalesce(excluded.property_type, lots.property_type),
    bedrooms        = coalesce(excluded.bedrooms, lots.bedrooms),
    scraped_at      = now()
returning id"""

EPC_UPSERT = """
insert into lot_epc (lot_id, uprn, floor_area_m2, construction_age_band,
                     epc_rating, epc_property_type, match_confidence)
values (%s,%s,%s,%s,%s,%s,%s)
on conflict (lot_id) do update set
    uprn = excluded.uprn, floor_area_m2 = excluded.floor_area_m2,
    construction_age_band = excluded.construction_age_band,
    epc_rating = excluded.epc_rating, epc_property_type = excluded.epc_property_type,
    match_confidence = excluded.match_confidence"""

ANALYSIS_UPSERT = """
insert into lot_analysis (lot_id, condition_class, condition_flags, prior_sale_price,
                          prior_sale_date, comp_count, comp_median_price, discount_pct,
                          reoffer_count, computed_at)
values (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
on conflict (lot_id) do update set
    condition_class = excluded.condition_class, condition_flags = excluded.condition_flags,
    prior_sale_price = excluded.prior_sale_price, prior_sale_date = excluded.prior_sale_date,
    comp_count = excluded.comp_count, comp_median_price = excluded.comp_median_price,
    discount_pct = excluded.discount_pct, reoffer_count = excluded.reoffer_count,
    computed_at = now()"""


def reoffer_count(conn, property_key: str | None, auction_date) -> int:
    """How many times this exact property appeared in EARLIER auctions.

    The README calls this the strongest distressed/stale signal, but the column
    was never populated by the original pipeline — so it is computed here.
    """
    if not (property_key and auction_date):
        return 0
    with conn.cursor() as cur:
        cur.execute(
            """select count(*) from lots
               where property_key = %s and auction_date < %s""",
            (property_key, auction_date),
        )
        return cur.fetchone()[0]


LOT_FIELDS = (
    "source", "source_lot_id", "lot_url", "auction_date", "first_seen", "listed_at",
    "address_raw", "postcode", "postcode_sector", "property_key", "guide_price",
    "guide_price_max", "hammer_price", "status", "result_raw", "description",
    "property_type", "bedrooms",
)


def upsert_lot(conn, lot: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(LOT_UPSERT, {k: lot.get(k) for k in LOT_FIELDS})
        return cur.fetchone()[0]


# --------------------------------------------------------------------- main ---
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", default="lots.jsonl")
    ap.add_argument("--load-ppd", help="Path to a Price Paid CSV to load, then exit")
    ap.add_argument("--no-db", action="store_true",
                    help="Skip all database work; classify conditions and print only")
    ap.add_argument("--no-epc", action="store_true", help="Skip EPC API lookups")
    ap.add_argument("--limit", type=int, help="Only process the first N lots")
    args = ap.parse_args()

    if args.load_ppd and args.no_db:
        sys.exit("--load-ppd needs a database; drop --no-db")

    conn = None
    if not args.no_db:
        # Only require a database when one is actually going to be used — the
        # original connected before it knew whether it needed to.
        if psycopg2 is None:
            sys.exit("pip install psycopg2-binary")
        if not os.environ.get("DATABASE_URL"):
            sys.exit("DATABASE_URL is not set (use --no-db for a classifier-only dry run)")
        conn = psycopg2.connect(os.environ["DATABASE_URL"])

    if args.load_ppd:
        load_ppd(conn, args.load_ppd)
        conn.close()
        return

    with open(args.lots, encoding="utf-8") as f:
        lots = [json.loads(line) for line in f if line.strip()]
    if args.limit:
        lots = lots[: args.limit]

    # HPI series are loaded lazily per local authority and reused across lots;
    # a national run touches a few hundred areas, not one per lot.
    forced_area = os.environ.get("HPI_AREA_CODE")
    ratio_cache: dict[str, dict] = {}
    area_cache: dict[str, str | None] = {}
    if conn and forced_area:
        ratio_cache[forced_area] = load_hpi_ratios(conn, forced_area)
        print(f"  (HPI_AREA_CODE set — forcing every lot onto {forced_area})",
              file=sys.stderr)

    session = requests.Session()
    for lot in lots:
        condition, flags = classify_condition(lot.get("description", ""))
        epc = {} if args.no_epc else (
            epc_lookup(lot.get("postcode"), lot.get("address_raw", ""), session) or {})

        if conn:
            area = forced_area or hpi_area_for(conn, lot.get("postcode"), area_cache)
            if area not in ratio_cache:
                ratio_cache[area] = load_hpi_ratios(conn, area)
            prior = prior_sales(conn, lot.get("postcode"), lot.get("address_raw", ""))
            comps = sector_comps(conn, lot.get("postcode_sector"),
                                 lot.get("property_type"), ratio_cache[area])
            reoffers = reoffer_count(conn, lot.get("property_key"), lot.get("auction_date"))
        else:
            prior, comps, reoffers = {}, {"comp_count": 0, "comp_median_price": None}, 0

        discount = None
        if lot.get("hammer_price") and comps["comp_median_price"]:
            discount = round(
                (comps["comp_median_price"] - lot["hammer_price"])
                / comps["comp_median_price"] * 100, 1)

        if conn:
            lot_id = upsert_lot(conn, lot)
            with conn.cursor() as cur:
                if epc:
                    cur.execute(EPC_UPSERT, (
                        lot_id, epc.get("uprn"), epc.get("floor_area_m2"),
                        epc.get("construction_age_band"), epc.get("epc_rating"),
                        epc.get("epc_property_type"), epc.get("match_confidence")))
                cur.execute(ANALYSIS_UPSERT, (
                    lot_id, condition, flags, prior.get("prior_sale_price"),
                    prior.get("prior_sale_date"), comps["comp_count"],
                    comps["comp_median_price"], discount, reoffers))
            conn.commit()

        print(json.dumps({
            "address": lot.get("address_raw"),
            "guide": lot.get("guide_price"),
            "hammer": lot.get("hammer_price"),
            "status": lot.get("status"),
            "condition": condition,
            "flags": flags,
            "reoffer_count": reoffers,
            **epc,
            **{k: (str(v) if k == "prior_sale_date" else v) for k, v in prior.items()},
            **comps,
            "discount_pct": discount,
        }))

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
