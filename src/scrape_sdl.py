"""SDL Property Auctions — past results scraper.

Verified against the live site on 2026-07-30. Notes on how it actually works,
because the obvious approach does not:

  * The event page (/auction/{id}/{slug}/) renders an EMPTY lot container
    (<div class="property-listings" id="searchView"></div>). Scraping that HTML
    with BeautifulSoup returns zero lots. So does POSTing the visible search form
    to /search. The cards are injected client-side.
  * The real source is an admin-ajax-style theme endpoint, AJAX_URL below, called
    with func=ajaxProp and a urlencoded querystring in `data`.
  * `limit=All` in that querystring returns every lot in ONE response (224 for a
    typical event), so a full 33-event backfill is ~33 requests, not thousands.

Results ARE published: the card's .status carries e.g. 'Sold at Auction £72,000'.
Note that 'Sold Prior to Auction' lots publish no price — roughly a quarter of
lots sell that way, so hammer_price is legitimately null for them.

Lot descriptions are NOT on the cards. They live on each /property/{id}/ page,
which is one extra request per lot — opt in with --with-descriptions.

Etiquette: 1 request every DELAY_S seconds, real UA with contact email, only
public pages. robots.txt allows the paths used here for a generic user-agent.
"""

import argparse
import dataclasses
import json
import re
import sys
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

from common import (
    classify_status,
    make_keys,
    parse_postcode,
    parse_price_range,
    property_type_code,
)

BASE = "https://www.sdlauctions.co.uk"
RESULTS_INDEX = f"{BASE}/property-auctions/past-auctions/"
AJAX_URL = f"{BASE}/wp-content/themes/sdl-auctions/library/property-functions.php"
DELAY_S = 3.0
HEADERS = {
    # Real contact address — polite scraping practice, and what the site owner
    # would use to reach us if they want the bot to stop.
    "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
AJAX_HEADERS = {**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/"}

# Event links look like /auction/1267/live-streamed-auction-2025-01-30/ — the
# auction date is in the slug, which is where auction_date comes from.
EVENT_RE = re.compile(r"/auction/(\d+)/([a-z0-9\-]*?(\d{4}-\d{2}-\d{2}))/", re.I)

SELECTORS = {
    "card": ".auction-card",
    "status": ".auction-card--title .status strong",
    "result": ".auction-card--content-result",
    "title": ".auction-card--content-title a",
    "address": ".auction-card--contend-address",   # sic: SDL's own typo
    "guide_label": ".auction-card--guide-price",
    "list_items": ".auction-card--content-list li",
    "beds": ".auction-meta li span",
    "description": ".entry-content",               # on /property/{id}/ pages only
}


@dataclasses.dataclass
class LotRecord:
    source: str
    source_lot_id: str
    lot_url: str
    auction_date: str | None
    address_raw: str
    postcode: str | None
    postcode_sector: str | None
    property_key: str | None
    guide_price: int | None
    hammer_price: int | None
    status: str
    description: str
    guide_price_max: int | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    result_raw: str = ""
    listed_at: str | None = None
    first_seen: str = dataclasses.field(default_factory=lambda: date.today().isoformat())


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(DELAY_S)
    return r.text


def fetch_lots_html(auction_id: str) -> str:
    """One POST returns every lot for the event (limit=All)."""
    inner = (
        "location=&radius=3&minBeds=&maxBeds=&minPrice=&maxPrice="
        f"&auctionId={auction_id}&include%5B%5D=&lat=&lng=&bounds="
        "&tempType=auction&search=1&limit=All&page=1&order=Lot+Number&oos=0"
    )
    r = requests.post(
        AJAX_URL, data={"func": "ajaxProp", "data": inner},
        headers=AJAX_HEADERS, timeout=60,
    )
    r.raise_for_status()
    time.sleep(DELAY_S)
    return r.text


def parse_events(html: str) -> list[dict]:
    """Event id, url and date, taken from the /auction/{id}/{slug-with-date}/ links."""
    events, seen = [], set()
    for m in EVENT_RE.finditer(html):
        auction_id, slug, iso = m.group(1), m.group(2), m.group(3)
        if auction_id in seen:
            continue
        seen.add(auction_id)
        events.append({
            "auction_id": auction_id,
            "auction_date": iso,
            "url": f"{BASE}/auction/{auction_id}/{slug}/",
        })
    events.sort(key=lambda e: e["auction_date"], reverse=True)
    return events


def _guide_from_items(items: list[str]) -> tuple[int | None, int | None]:
    """The guide value is the <li> AFTER the 'Guide price*' label <li>."""
    for i, text in enumerate(items):
        if re.search(r"guide price|starting bid|current bid", text, re.I):
            if i + 1 < len(items):
                return parse_price_range(items[i + 1])
    return None, None


def parse_cards(html: str, auction_date: str | None) -> list[LotRecord]:
    soup = BeautifulSoup(html, "html.parser")
    lots = []
    for card in soup.select(SELECTORS["card"]):
        addr_el = card.select_one(SELECTORS["address"])
        if not addr_el:
            continue
        address = addr_el.get_text(" ", strip=True)

        status_el = card.select_one(SELECTORS["status"]) or card.select_one(SELECTORS["result"])
        result_text = status_el.get_text(" ", strip=True) if status_el else ""
        status, hammer = classify_status(result_text)

        items = [li.get_text(" ", strip=True)
                 for li in card.select(SELECTORS["list_items"])]
        guide, guide_max = _guide_from_items(items)

        title_el = card.select_one(SELECTORS["title"])
        title = title_el.get_text(" ", strip=True) if title_el else ""
        lot_url = (title_el.get("href") or "") if title_el else ""
        if lot_url.startswith("/"):
            lot_url = BASE + lot_url

        beds_el = card.select_one(SELECTORS["beds"])
        try:
            beds = int(beds_el.get_text(strip=True)) if beds_el else None
        except ValueError:
            beds = None

        postcode = parse_postcode(address)
        sector, prop_key = make_keys(address, postcode)

        lots.append(LotRecord(
            source="sdl",
            source_lot_id=card.get("data-id") or lot_url or address,
            lot_url=lot_url,
            auction_date=auction_date,
            address_raw=address,
            postcode=postcode,
            postcode_sector=sector,
            property_key=prop_key,
            guide_price=guide,
            guide_price_max=guide_max,
            hammer_price=hammer,
            status=status,
            result_raw=result_text,
            description="",
            property_type=property_type_code(title),
            bedrooms=beds,
            listed_at=(card.get("data-date") or "")[:10] or None,
        ))
    return lots


def fetch_description(lot_url: str) -> str:
    """Descriptions are only on the individual property page — 1 request each."""
    if not lot_url:
        return ""
    try:
        el = BeautifulSoup(fetch(lot_url), "html.parser").select_one(SELECTORS["description"])
    except Exception as e:
        print(f"  ! description {lot_url}: {e}", file=sys.stderr)
        return ""
    if not el:
        return ""
    text = el.get_text(" ", strip=True)
    # Cards and detail pages both prefix with the type; the useful copy starts
    # after "Property Description:".
    m = re.search(r"property description:\s*(.+)", text, re.I | re.S)
    return (m.group(1) if m else text).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", help="Fetch one URL and save raw HTML to probe.html")
    ap.add_argument("--max-events", type=int, default=3,
                    help="How many of the most recent events to scrape (0 = all)")
    ap.add_argument("--auction-id", help="Scrape one specific auction id and exit")
    ap.add_argument("--with-descriptions", action="store_true",
                    help="Also fetch each lot's detail page for description text "
                         "(~1 extra request per lot; a full event is ~224)")
    ap.add_argument("--out", default="lots.jsonl")
    args = ap.parse_args()

    if args.probe:
        # encoding is not optional here: auction pages are full of £ and the
        # Windows default (cp1252) raises UnicodeEncodeError on write.
        with open("probe.html", "w", encoding="utf-8") as f:
            f.write(fetch(args.probe))
        print("Saved probe.html")
        return

    events = parse_events(fetch(RESULTS_INDEX))
    print(f"Found {len(events)} auction events")
    if args.auction_id:
        # Still resolve via the index so auction_date comes from the slug rather
        # than being left null (it is part of the lots unique key).
        events = [e for e in events if e["auction_id"] == args.auction_id] or [
            {"auction_id": args.auction_id, "auction_date": None,
             "url": f"{BASE}/auction/{args.auction_id}/"}]
    elif args.max_events:
        events = events[: args.max_events]

    all_lots: list[LotRecord] = []
    for ev in events:
        try:
            lots = parse_cards(fetch_lots_html(ev["auction_id"]), ev["auction_date"])
        except Exception as e:
            print(f"  ! auction {ev['auction_id']}: {e}", file=sys.stderr)
            continue
        print(f"  auction {ev['auction_id']} ({ev['auction_date']}): {len(lots)} lots")
        if args.with_descriptions:
            for lot in lots:
                lot.description = fetch_description(lot.lot_url)
        all_lots.extend(lots)

    with open(args.out, "w", encoding="utf-8") as f:
        for lot in all_lots:
            f.write(json.dumps(dataclasses.asdict(lot)) + "\n")

    sold = sum(1 for l in all_lots if l.hammer_price)
    print(f"Wrote {len(all_lots)} lots → {args.out} ({sold} with a hammer price)")


if __name__ == "__main__":
    main()
