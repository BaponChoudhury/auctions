"""Clive Emson Auctioneers — past results scraper.

Verified against the live site on 2026-07-31. Emits the same LotRecord shape as
the other scrapers.

Added specifically to correct the corpus's Midlands bias: Clive Emson is a
southern house (Kent, Sussex, Surrey, Hampshire, Essex, London, West Country).

  * robots.txt is `Disallow:` (nothing blocked) but sets **Crawl-Delay: 10**.
    DELAY_S honours that — this scraper is deliberately 3x slower than the others.
  * /future/results/ lists 24 past auctions as /properties/{id}/ links.
  * Each results page is server-rendered and carries every lot in ONE request,
    with all the data in attributes on `.lot`:
        data-lot, data-ceastatus, data-price, data-loc, data-lonlat, data-cathead
    Each lot appears TWICE in the DOM (list view and map view), so dedupe on
    (data-auc, data-lot) or the counts double.

Two things this source does differently:

  * It publishes a price for "Sold Prior" lots (17/17 in the sample) — the only
    one of the four that does. Bond Wolfe, SDL and Allsop all withhold it.
  * The results page has NO street address or postcode, only a town-county
    string and a lat/lon. The postcode is recovered by reverse-geocoding that
    coordinate through postcodes.io, which is accurate: spot-checked against a
    lot detail page, the coordinate resolved to the correct postcode at 6m.
    `postcode_distance_m` records how far the match was so low-confidence ones
    can be filtered.

Because there is no house number, lots from this source get **no property_key**
and cannot be matched to Land Registry PPD. Use `--with-addresses` to fetch each
lot's detail page for the real address — correct but expensive: ~166 lots per
auction at 10s each is roughly 28 minutes per auction.
"""

import argparse
import dataclasses
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from common import make_keys, parse_postcode
from scrape_sdl import LotRecord

BASE = "https://www.cliveemson.co.uk"
RESULTS_INDEX = f"{BASE}/future/results/"
POSTCODES_IO = "https://api.postcodes.io/postcodes"
# robots.txt: "Crawl-Delay: 10". Do not lower this.
DELAY_S = 10.0
HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}

AUCTION_RE = re.compile(r'href="/properties/(\d+)/"')
DATE_RE = re.compile(r"Auction Date:\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", re.I)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# A reverse-geocoded postcode further than this from the lot is not trustworthy.
MAX_GEO_DISTANCE_M = 150

_TYPE_PATTERNS = [
    (r"\bterrac|\bmid[- ]terrace|\bend[- ]of[- ]terrace", "T"),
    (r"semi[- ]detached", "S"),
    (r"\bdetached\b|\bbungalow\b", "D"),
    (r"\bflat\b|\bapartment|\bmaisonette|\bstudio\b", "F"),
    (r"\bland\b|\bcommercial|\bshop\b|\bretail|\boffice|\bgarage|\bwoodland|"
     r"\bground rent|\bindustrial|\bsite\b|\bplot\b|\bpub\b|\binvestment\b", "O"),
]


def classify_status(raw: str) -> str:
    """Clive Emson's own wording, mapped onto the shared vocabulary."""
    t = (raw or "").strip().lower()
    # "unsold" contains "sold": test it, and the re-entry wording, first.
    if "unsold" in t or t.startswith("available in our"):
        return "unsold"
    if "withdrawn" in t:
        return "withdrawn"
    if "postponed" in t:
        return "postponed"
    if "prior" in t:
        return "sold_prior"
    if "after" in t:
        return "sold_after"
    if "sold" in t:
        return "sold"
    return "listed"


def parse_price(raw: str) -> int | None:
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else None


def property_type(heading: str) -> str | None:
    t = (heading or "").lower()
    for pat, code in _TYPE_PATTERNS:
        if re.search(pat, t):
            return code
    if re.search(r"\bhouse\b|\bhome\b|\bcottage\b", t):
        return None    # a house with no stated built form; do not guess
    return None


def fetch(session, url: str) -> str:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    time.sleep(DELAY_S)
    return r.text


def parse_auction_ids(html: str) -> list[str]:
    ids, seen = [], set()
    for m in AUCTION_RE.finditer(html):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            ids.append(m.group(1))
    return ids


def auction_date_from_lot_page(session, auction_id: str, lot_no: str) -> str | None:
    """The results page gives only a month, so read the exact date off one lot."""
    try:
        html = fetch(session, f"{BASE}/properties/{auction_id}/{lot_no}/")
    except requests.RequestException as e:
        print(f"  ! date lookup {auction_id}/{lot_no}: {e}", file=sys.stderr)
        return None
    m = DATE_RE.search(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    if not m:
        return None
    mon = MONTHS.get(m.group(2)[:3].lower())
    return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}" if mon else None


def reverse_geocode(session, lots: list[LotRecord], coords: dict) -> None:
    """Recover postcodes from lat/lon in bulk (postcodes.io, free, 100 per call)."""
    keyed = [(l, coords.get(l.source_lot_id)) for l in lots]
    todo = [(l, c) for l, c in keyed if c]
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        payload = {"geolocations": [{"latitude": c[0], "longitude": c[1],
                                     "limit": 1, "radius": 1000} for _, c in chunk]}
        try:
            r = session.post(POSTCODES_IO, json=payload, timeout=45)
            results = r.json()["result"]
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  ! reverse geocode: {e}", file=sys.stderr)
            continue
        for (lot, _), item in zip(chunk, results):
            hits = item.get("result") or []
            if not hits:
                continue
            best = hits[0]
            if best.get("distance", 1e9) > MAX_GEO_DISTANCE_M:
                continue
            lot.postcode = best["postcode"]
            lot.postcode_sector = f"{best['postcode'].split()[0]} {best['postcode'].split()[1][0]}"
        time.sleep(1)


def parse_results(html: str, auction_id: str, auction_date: str | None):
    soup = BeautifulSoup(html, "html.parser")
    lots, coords, seen = [], {}, set()
    for el in soup.select(".lot"):
        lot_no = el.get("data-lot")
        if not lot_no or lot_no in seen:
            continue    # each lot appears twice: list view and map view
        seen.add(lot_no)

        status = classify_status(el.get("data-ceastatus"))
        price = parse_price(el.get("data-price"))
        heading = (el.get("data-cathead") or "").strip()
        loc = (el.get("data-loc") or "").strip()

        lot_id = f"{auction_id}-{lot_no}"
        lonlat = (el.get("data-lonlat") or "").split(",")
        if len(lonlat) == 2:
            try:
                coords[lot_id] = (float(lonlat[0]), float(lonlat[1]))
            except ValueError:
                pass

        lots.append(LotRecord(
            source="emson",
            source_lot_id=lot_id,
            lot_url=f"{BASE}/properties/{auction_id}/{lot_no}/",
            auction_date=auction_date,
            # The results page has no street address; this is town - county.
            address_raw=f"{heading} — {loc}" if heading else loc,
            postcode=None,          # filled in by reverse_geocode()
            postcode_sector=None,
            property_key=None,      # no house number available from this page
            guide_price=None,       # not published on the results page
            hammer_price=price if status in ("sold", "sold_prior", "sold_after") else None,
            status=status,
            result_raw="; ".join(filter(None, [el.get("data-ceastatus"), loc])),
            description=heading,
            property_type=property_type(heading),
            bedrooms=None,
            listed_at=None,
        ))
    return lots, coords


def enrich_with_addresses(session, lots: list[LotRecord]) -> None:
    """Fetch each lot's detail page for the real address (10s per lot)."""
    for i, lot in enumerate(lots, 1):
        try:
            html = fetch(session, lot.lot_url)
        except requests.RequestException as e:
            print(f"  ! {lot.lot_url}: {e}", file=sys.stderr)
            continue
        soup = BeautifulSoup(html, "html.parser")
        h2 = soup.find("h2")
        addr = h2.get_text(" ", strip=True) if h2 else ""
        pc = parse_postcode(addr)
        if pc:
            lot.address_raw = addr
            lot.postcode = pc
            lot.postcode_sector, lot.property_key = make_keys(addr, pc)
        if i % 25 == 0:
            print(f"    addresses {i}/{len(lots)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-events", type=int, default=2,
                    help="How many of the most recent past auctions (0 = all)")
    ap.add_argument("--auction-id")
    ap.add_argument("--with-addresses", action="store_true",
                    help="Fetch each lot's detail page for the real address and "
                         "house number (~28 min per auction at the 10s crawl delay)")
    ap.add_argument("--out", default="emson.jsonl")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    if args.auction_id:
        ids = [args.auction_id]
    else:
        ids = parse_auction_ids(fetch(session, RESULTS_INDEX))
        print(f"Found {len(ids)} past auctions")
        if args.max_events:
            ids = ids[: args.max_events]

    all_lots: list[LotRecord] = []
    for aid in ids:
        try:
            html = fetch(session, f"{BASE}/properties/{aid}/")
        except requests.RequestException as e:
            print(f"  ! auction {aid}: {e}", file=sys.stderr)
            continue
        lots, coords = parse_results(html, aid, None)
        if not lots:
            print(f"  auction {aid}: no lots")
            continue
        # One extra request gets the exact date for the whole auction.
        adate = auction_date_from_lot_page(session, aid, lots[0].source_lot_id.split("-")[1])
        for lot in lots:
            lot.auction_date = adate
        if args.with_addresses:
            enrich_with_addresses(session, lots)
        else:
            reverse_geocode(session, lots, coords)
        got_pc = sum(1 for l in lots if l.postcode)
        print(f"  auction {aid} ({adate}): {len(lots)} lots, {got_pc} with a postcode")
        all_lots.extend(lots)

    with open(args.out, "w", encoding="utf-8") as f:
        for lot in all_lots:
            f.write(json.dumps(dataclasses.asdict(lot)) + "\n")
    sold = sum(1 for l in all_lots if l.hammer_price)
    print(f"Wrote {len(all_lots)} lots → {args.out} ({sold} with a hammer price)")


if __name__ == "__main__":
    main()
