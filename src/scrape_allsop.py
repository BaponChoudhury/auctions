"""Allsop — past auction results scraper.

Verified against the live site on 2026-07-31. Emits the same LotRecord shape as
the other scrapers so enrich.py and the schema work unchanged.

Allsop is the easiest of the three sources and the most complete:

  * /auctions/past-auction-results/ lists past events as
    /property-search?auction_id=<uuid> links.
  * The site is a React SPA, but it is backed by a clean JSON API:
    GET /api/search?auction_id=<uuid>&size=<n>
    `size` returns the whole auction in ONE request (page=N also works).
  * robots.txt is a single Sitemap: line — no restrictions at all.

Unlike the other two it publishes BOTH a guide price and a sale price, plus
per-lot feature bullets, so it is the only source that can support a
sold-vs-guide figure and condition classification without extra requests.

Allsop is London/national and runs commercial as well as residential catalogues,
which is the point of adding it: SDL and Bond Wolfe are both Midlands-based.
"""

import argparse
import dataclasses
import json
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from common import make_keys, parse_postcode
from scrape_sdl import LotRecord

BASE = "https://www.allsop.co.uk"
PAST_INDEX = f"{BASE}/auctions/past-auction-results/"
API = f"{BASE}/api/search"
DELAY_S = 3.0
PAGE_SIZE = 500
HEADERS = {
    "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
}

EVENT_RE = re.compile(r"/property-search\?auction_id=([0-9a-f\-]{16,})")
# Needs the `tzdata` package on Windows, which has no system tz database.
UK = ZoneInfo("Europe/London")

# Allsop's own lot status wording, mapped onto the shared vocabulary.
_STATUS = {
    "sold": "sold",
    "sold prior": "sold_prior",
    "sold after": "sold_after",
    "withdrawn": "withdrawn",
    "postponed": "postponed",
    "available": "unsold",       # on a PAST auction, still-available means it did not sell
    "unsold": "unsold",
    "remains available": "unsold",
}

# Allsop tags each lot with its own type vocabulary; map to PPD codes.
# Order matters: "semi-detached" contains "detached", so it must be tested first.
_TYPE_PATTERNS = [
    (r"terrac", "T"),
    (r"semi[\s\-]?detached", "S"),
    (r"detached", "D"),
    (r"flat|apartment|maisonette|studio", "F"),
    (r"retail|shop|office|commercial|industrial|warehouse|land|garage|mixed|"
     r"hotel|pub|leisure|block|development|motor trade|ground rent|medical", "O"),
]
# The residential catalogue labels most lots as a bare "House" with no built
# form, but the byline spells it out ("Freehold Mid Terrace House", "Link
# Detached House"). Without this fallback, 133 of 301 lots in one residential
# auction had no type at all, which drops them out of like-for-like comps.
_GENERIC_TYPES = {"house", "other", "development"}


def classify_status(raw: str, sale_price) -> tuple[str, int | None]:
    """Map lot status; only trust a price on a status that means it sold."""
    t = (raw or "").strip().lower()
    # "unsold" contains "sold" — match the longest/most specific key first.
    status = "listed"
    for key in sorted(_STATUS, key=len, reverse=True):
        if key in t:
            status = _STATUS[key]
            break
    price = None
    if status in ("sold", "sold_prior", "sold_after"):
        try:
            price = int(float(sale_price)) if sale_price not in (None, "") else None
        except (TypeError, ValueError):
            price = None
    return status, price


def _match_type(blob: str) -> str | None:
    for pat, code in _TYPE_PATTERNS:
        if re.search(pat, blob):
            return code
    return None


def property_type(lot: dict) -> str | None:
    types = []
    for key in ("residential_property_types", "resi_property_types",
                "commercial_property_types", "comm_property_types",
                "allsop_propertytype", "property_types"):
        v = lot.get(key)
        if isinstance(v, list):
            types += [str(x) for x in v]
        elif isinstance(v, str) and v:
            types.append(v)

    labels = {t.strip().lower() for t in types if t}
    code = _match_type(" ".join(labels))
    if code:
        return code

    # Structured labels were absent or purely generic ("House"): fall back to the
    # byline, which is where the residential catalogue states the built form.
    if not labels or labels <= _GENERIC_TYPES:
        byline = " ".join(str(lot.get(k) or "") for k in
                          ("main_byline", "property_byline", "allsop_propertybyline")).lower()
        code = _match_type(byline)
        if code:
            return code
    return None


def auction_date(lot: dict) -> str | None:
    """auction_date arrives as epoch milliseconds at UK-LOCAL midnight.

    It must be read back in Europe/London, not UTC. During BST that timestamp is
    23:00Z the previous day, so a UTC conversion silently reports every summer
    auction one day early — verified against Allsop's own published dates, where
    the winter events (Feb, Mar) agreed and every BST event was off by one.
    A wrong auction_date corrupts the lots unique key and any time series.
    """
    v = lot.get("auction_date")
    if v in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=UK).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def description(lot: dict) -> str:
    """Feature bullets plus the byline — enough for the condition classifier."""
    parts = []
    byline = lot.get("main_byline") or lot.get("property_byline") or lot.get("allsop_propertybyline")
    if byline:
        parts.append(str(byline))
    feats = lot.get("features")
    if isinstance(feats, list):
        parts += [str(f) for f in feats if f]
    elif isinstance(feats, str) and feats:
        parts.append(feats)
    return ". ".join(parts).strip()


def _int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_lots(results: list[dict]) -> list[LotRecord]:
    lots = []
    for lot in results:
        if not lot.get("allsop_lotid"):
            continue    # non-auction rows (investment/leasing listings) share this index
        address = (lot.get("allsop_address") or lot.get("full_address") or "").strip()
        if not address:
            continue
        postcode = (lot.get("allsop_propertypostcode") or lot.get("postcode")
                    or parse_postcode(address))
        postcode = parse_postcode(postcode or "") or parse_postcode(address)
        sector, prop_key = make_keys(address, postcode)

        status, hammer = classify_status(
            lot.get("allsop_lotstatus") or lot.get("lot_status") or lot.get("lotStatus"),
            lot.get("sale_price"))

        lots.append(LotRecord(
            source="allsop",
            source_lot_id=str(lot["allsop_lotid"]),
            lot_url=f"{BASE}/lot-overview?versionId={lot.get('version_id') or lot['allsop_lotid']}",
            auction_date=auction_date(lot),
            address_raw=address,
            postcode=postcode,
            postcode_sector=sector,
            property_key=prop_key,
            guide_price=_int(lot.get("guide_price_lower")),
            guide_price_max=_int(lot.get("guide_price_upper")),
            hammer_price=hammer,
            status=status,
            result_raw="; ".join(filter(None, [
                str(lot.get("allsop_lotstatus") or ""),
                str(lot.get("guide_price_text") or ""),
                str(lot.get("catalogue_type") or "")])),
            description=description(lot),
            property_type=property_type(lot),
            bedrooms=None,
            listed_at=(str(lot.get("market_from_date") or "")[:10] or None),
        ))
    return lots


def fetch_json(session, url, params=None):
    r = session.get(url, params=params, timeout=60)
    r.raise_for_status()
    time.sleep(DELAY_S)
    return r.json()


def fetch_event_ids(session) -> list[str]:
    r = session.get(PAST_INDEX, headers={"Accept": "text/html"}, timeout=30)
    r.raise_for_status()
    time.sleep(DELAY_S)
    ids, seen = [], set()
    for m in EVENT_RE.finditer(r.text):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            ids.append(m.group(1))
    return ids


def fetch_auction(session, auction_id: str) -> list[LotRecord]:
    """`size` returns the whole auction in one request; page as a fallback."""
    payload = fetch_json(session, API, {"auction_id": auction_id, "size": PAGE_SIZE})
    data = payload.get("data") or {}
    results = data.get("results") or []
    total = data.get("total") or len(results)

    if len(results) < total:      # size was capped — fall back to paging
        page, seen = 2, {id(r) for r in results}
        while len(results) < total and page < 60:
            more = ((fetch_json(session, API,
                                {"auction_id": auction_id, "page": page}).get("data") or {})
                    .get("results") or [])
            if not more:
                break
            results += more
            page += 1
    return parse_lots(results)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-events", type=int, default=3,
                    help="How many of the most recent past auctions to scrape (0 = all)")
    ap.add_argument("--auction-id", help="Scrape one specific auction id")
    ap.add_argument("--out", default="allsop.jsonl")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    if args.auction_id:
        ids = [args.auction_id]
    else:
        ids = fetch_event_ids(session)
        print(f"Found {len(ids)} past auctions")
        if args.max_events:
            ids = ids[: args.max_events]

    all_lots: list[LotRecord] = []
    for aid in ids:
        try:
            lots = fetch_auction(session, aid)
        except Exception as e:
            print(f"  ! auction {aid}: {e}", file=sys.stderr)
            continue
        date = next((l.auction_date for l in lots if l.auction_date), None)
        print(f"  auction {aid[:8]} ({date}): {len(lots)} lots")
        all_lots.extend(lots)

    with open(args.out, "w", encoding="utf-8") as f:
        for lot in all_lots:
            f.write(json.dumps(dataclasses.asdict(lot)) + "\n")
    sold = sum(1 for l in all_lots if l.hammer_price)
    print(f"Wrote {len(all_lots)} lots → {args.out} ({sold} with a hammer price)")


if __name__ == "__main__":
    main()
