"""Bond Wolfe Auctions — past results scraper.

Verified against the live site on 2026-07-30. Emits the same LotRecord shape as
scrape_sdl.py so enrich.py and the schema work unchanged.

How it works (same shape of problem as SDL — the listing is client-side):
  * /property-auctions-west-midlands/past-property-auctions/ lists past events as
    /auction/{id}/ links.
  * Lots come from WordPress admin-ajax with action=get_properties. The call is
    nonce-protected: `tjdPropertyAjax` is localised into every event page and
    carries both ajaxurl and ajaxnonce, so fetch the event page first.
  * postsperpage=All returns HTTP 500 from their end — paginate at 96 instead.

Differences from SDL worth knowing before comparing the two sources:
  * Past Bond Wolfe results publish the SOLD price but NOT the guide price, so
    guide_price is null here and uplift-vs-guide cannot be computed. SDL
    publishes both. Do not average the two sources together on that metric.
  * Bond Wolfe tags lots with condition/tenure badges ("Renovation", "Vacant",
    "Investment"), which are captured verbatim in result_raw.
"""

import argparse
import dataclasses
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from common import make_keys, parse_postcode, parse_price
from scrape_sdl import LotRecord

BASE = "https://www.bondwolfe.com"
PAST_INDEX = f"{BASE}/property-auctions-west-midlands/past-property-auctions/"
DELAY_S = 3.0
PER_PAGE = 96
HEADERS = {
    "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

EVENT_RE = re.compile(r"/auction/(\d+)/")
NONCE_RE = re.compile(r"tjdPropertyAjax\s*=\s*(\{.*?\})\s*;", re.S)
DATE_RE = re.compile(r"Auction:\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", re.I)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

SELECTORS = {
    "card": ".PropertyCard",
    "status": ".PropertyCard-tag",
    "lotnum": ".PropertyCard-detail-lotnum",
    "address": ".PropertyCard-detail-description",
    "tagline": ".PropertyCard-detail-tagline",
    "price": ".PropertyCard-detail-price",
    "date": ".PropertyCard-detail-date",
    "badge": ".Badge",
}

# Built from the site's own tagline wording, mapped to PPD codes like scrape_sdl.
_TYPE_PATTERNS = [
    (r"\bmid[- ]terrac|\bterrac|\btown house", "T"),
    (r"\bsemi[- ]detached", "S"),
    (r"\bdetached", "D"),
    (r"\bflat\b|\bapartment|\bmaisonette|\bstudio", "F"),
    (r"\bland\b|\bcommercial|\bretail|\bshop\b|\bwarehouse|\boffice|"
     r"\bgarage|\bindustrial|\bblock of|\bsite\b|\bpub\b|\bhotel", "O"),
]


def parse_type(tagline: str) -> tuple[str | None, int | None]:
    """'3 bedroom mid terraced house in Stoke on Trent' -> ('T', 3)."""
    t = (tagline or "").lower()
    beds = None
    m = re.match(r"\s*(\d+)\s+bedroom", t)
    if m:
        beds = int(m.group(1))
    for pat, code in _TYPE_PATTERNS:
        if re.search(pat, t):
            return code, beds
    return None, beds


def classify_status(tag: str, price_text: str) -> tuple[str, int | None]:
    """Bond Wolfe's own status wording, mapped onto the shared vocabulary.

    Both strings are considered: unsold lots carry no .PropertyCard-tag at all and
    announce themselves only in the price block ("Unsold Auction: 9th Jul 2026").
    Reading the tag alone silently files every one of them as 'listed'.
    """
    t = f"{tag or ''} {price_text or ''}".strip().lower()
    # Only trust a figure that is attached to a sale. "Sold prior to auction, for
    # an undisclosed amount" is a real Bond Wolfe string and carries no price.
    price = parse_price(price_text) if re.search(r"sold\s+for", price_text or "", re.I) else None
    # "unsold" must be tested before "sold" — it contains it as a substring, and a
    # plain `"sold" in t` files every unsold lot as a sale.
    if re.search(r"\bunsold\b|\bavailable\b|\bremain", t):
        return "unsold", None
    if "prior" in t:
        return "sold_prior", price
    if "after" in t:
        return "sold_after", price
    if re.search(r"\bsold\b", t):
        return "sold", price
    if "withdrawn" in t:
        return "withdrawn", None
    if "postponed" in t:
        return "postponed", None
    return "listed", None


def parse_auction_date(text: str) -> str | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    mon = MONTHS.get(m.group(2)[:3].lower())
    return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}" if mon else None


def fetch(session, url: str) -> str:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    time.sleep(DELAY_S)
    return r.text


def parse_events(html: str) -> list[str]:
    seen, out = set(), []
    for m in EVENT_RE.finditer(html):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def fetch_lots_html(session, auction_id: str) -> list[str]:
    """Nonce lives on the event page, so fetch that first, then page the ajax."""
    event_url = f"{BASE}/auction/{auction_id}/"
    m = NONCE_RE.search(fetch(session, event_url))
    if not m:
        raise RuntimeError("tjdPropertyAjax nonce not found on event page")
    cfg = json.loads(m.group(1))

    pages, page = [], 1
    while True:
        r = session.post(
            cfg["ajaxurl"],
            data={"action": "get_properties", "page": str(page), "total_pages": "1",
                  "postsperpage": str(PER_PAGE), "orderby": "", "location": "", "radius": "",
                  "type": "", "minprice": "", "maxprice": "", "auction": auction_id,
                  "status": "", "get_map": "false", "security": cfg["ajaxnonce"]},
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": event_url},
            timeout=60,
        )
        time.sleep(DELAY_S)
        try:
            payload = r.json()
        except ValueError:
            raise RuntimeError(f"non-JSON from ajax (HTTP {r.status_code})")
        html = (payload.get("data") or {}).get("html") or ""
        if not payload.get("success") or not html:
            break
        pages.append(html)
        if len(BeautifulSoup(html, "html.parser").select(SELECTORS["card"])) < PER_PAGE:
            break
        page += 1
    return pages


def parse_cards(html: str) -> list[LotRecord]:
    soup = BeautifulSoup(html, "html.parser")
    lots = []
    for card in soup.select(SELECTORS["card"]):
        addr_el = card.select_one(SELECTORS["address"])
        if not addr_el:
            continue
        address = addr_el.get_text(" ", strip=True)

        tag_el = card.select_one(SELECTORS["status"])
        price_el = card.select_one(SELECTORS["price"])
        price_text = price_el.get_text(" ", strip=True) if price_el else ""
        status, hammer = classify_status(
            tag_el.get_text(" ", strip=True) if tag_el else "", price_text)

        tagline_el = card.select_one(SELECTORS["tagline"])
        tagline = tagline_el.get_text(" ", strip=True) if tagline_el else ""
        ptype, beds = parse_type(tagline)

        date_el = card.select_one(SELECTORS["date"])
        auction_date = parse_auction_date(date_el.get_text(" ", strip=True) if date_el else "")

        lot_el = card.select_one(SELECTORS["lotnum"])
        lot_no = (lot_el.get_text(" ", strip=True) if lot_el else "").replace("Lot", "").strip()

        badges = [b.get_text(" ", strip=True) for b in card.select(SELECTORS["badge"])]
        badges = [b for b in badges if b and "virtual tour" not in b.lower()]

        postcode = parse_postcode(address)
        sector, prop_key = make_keys(address, postcode)
        lot_url = card.get("href") or ""

        lots.append(LotRecord(
            source="bondwolfe",
            source_lot_id=card.get("id") or lot_url or address,
            lot_url=lot_url,
            auction_date=auction_date,
            address_raw=address,
            postcode=postcode,
            postcode_sector=sector,
            property_key=prop_key,
            # Past Bond Wolfe results publish the sale price but not the guide.
            guide_price=None,
            hammer_price=hammer,
            status=status,
            result_raw="; ".join(filter(None, [price_text] + badges)),
            description=tagline,
            property_type=ptype,
            bedrooms=beds,
            listed_at=None,
        ))
        lots[-1].source_lot_id = f"{lot_no or lots[-1].source_lot_id}"
    return lots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-events", type=int, default=2,
                    help="How many of the most recent past events to scrape (0 = all)")
    ap.add_argument("--auction-id", help="Scrape one specific auction id")
    ap.add_argument("--out", default="bondwolfe.jsonl")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    if args.auction_id:
        events = [args.auction_id]
    else:
        events = parse_events(fetch(session, PAST_INDEX))
        print(f"Found {len(events)} past auction events")
        if args.max_events:
            events = events[: args.max_events]

    all_lots: list[LotRecord] = []
    for aid in events:
        try:
            pages = fetch_lots_html(session, aid)
        except Exception as e:
            print(f"  ! auction {aid}: {e}", file=sys.stderr)
            continue
        lots = [lot for html in pages for lot in parse_cards(html)]
        date = next((l.auction_date for l in lots if l.auction_date), None)
        print(f"  auction {aid} ({date}): {len(lots)} lots over {len(pages)} page(s)")
        all_lots.extend(lots)

    with open(args.out, "w", encoding="utf-8") as f:
        for lot in all_lots:
            f.write(json.dumps(dataclasses.asdict(lot)) + "\n")
    sold = sum(1 for l in all_lots if l.hammer_price)
    print(f"Wrote {len(all_lots)} lots → {args.out} ({sold} with a hammer price)")


if __name__ == "__main__":
    main()
