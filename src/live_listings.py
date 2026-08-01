"""Find lots CURRENTLY for sale near a location.

The rest of this project analyses past results. This one asks the live
catalogues what is on right now, so the price ranges can be applied to
something you could actually bid on.

Bond Wolfe first, because it carries 81% of Stafford stock. Its get_properties
endpoint takes location + radius, which is exactly the query we want.

  python live_listings.py --location Stafford --radius 10
"""

import argparse
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from common import make_keys, parse_postcode
from scrape_bondwolfe import (BASE as BW_BASE, HEADERS, NONCE_RE, SELECTORS,
                              classify_status, parse_auction_date, parse_type)

DELAY_S = 3.0


def bw_live(session, location: str, radius: int) -> list[dict]:
    """Bond Wolfe's own search, filtered by location — same endpoint the site uses."""
    page_html = session.get(f"{BW_BASE}/auctions/properties/", timeout=45).text
    time.sleep(DELAY_S)
    m = NONCE_RE.search(page_html)
    if not m:
        print("  ! could not read Bond Wolfe's ajax nonce", file=sys.stderr)
        return []
    cfg = json.loads(m.group(1))

    out, page = [], 1
    while page <= 6:
        r = session.post(
            cfg["ajaxurl"],
            data={"action": "get_properties", "page": str(page), "total_pages": "1",
                  "postsperpage": "96", "orderby": "", "location": location,
                  "radius": str(radius), "type": "", "minprice": "", "maxprice": "",
                  "auction": "", "status": "", "get_map": "false",
                  "security": cfg["ajaxnonce"]},
            headers={"X-Requested-With": "XMLHttpRequest",
                     "Referer": f"{BW_BASE}/auctions/properties/"},
            timeout=60)
        time.sleep(DELAY_S)
        try:
            payload = r.json()
        except ValueError:
            print(f"  ! non-JSON from Bond Wolfe (HTTP {r.status_code})", file=sys.stderr)
            break
        html = (payload.get("data") or {}).get("html") or ""
        if not payload.get("success") or not html:
            note = re.sub(r"<[^>]+>", " ", html).strip()
            if note:
                print(f"  Bond Wolfe says: {note[:90]}")
            break
        cards = BeautifulSoup(html, "html.parser").select(SELECTORS["card"])
        if not cards:
            break
        for card in cards:
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
            adate = parse_auction_date(date_el.get_text(" ", strip=True) if date_el else "")
            pc = parse_postcode(address)
            out.append({
                "source": "Bond Wolfe", "address": address, "postcode": pc,
                "sector": make_keys(address, pc)[0], "type": ptype, "beds": beds,
                "status": status, "hammer": hammer, "auction_date": adate,
                "tagline": tagline, "raw": price_text,
                "url": card.get("href") or "",
            })
        if len(cards) < 96:
            break
        page += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default="Stafford")
    ap.add_argument("--radius", type=int, default=10)
    args = ap.parse_args()

    s = requests.Session()
    s.headers.update(HEADERS)
    print(f"searching Bond Wolfe: {args.location}, {args.radius} miles ...")
    lots = bw_live(s, args.location, args.radius)
    print(f"  {len(lots)} lots returned")

    # A live catalogue lot has no result yet; anything already sold is history.
    live = [l for l in lots if l["status"] in ("listed", "unsold")]
    print(f"  {len(live)} of them have no result yet (i.e. still available)\n")

    if not lots:
        print("Nothing returned. Bond Wolfe shows lots only while a catalogue is\n"
              "open; between auctions the search is empty. Try again nearer the\n"
              "next sale, or widen --radius.")
        return

    NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat",
            "O": "Land/comm"}
    for l in sorted(lots, key=lambda x: (x["auction_date"] or "", x["address"])):
        beds = f"{l['beds']}bed" if l["beds"] else "  ?  "
        print(f"  {str(l['auction_date']):11} {NAME.get(l['type'], '?'):10} {beds:6} "
              f"{str(l['postcode'] or ''):9} {l['status']:9} {l['address'][:44]}")
        if l["raw"]:
            print(f"              {l['raw'][:70]}")
        print(f"              {l['url']}")


if __name__ == "__main__":
    main()
