"""What is on RIGHT NOW, across every house, near a given area.

Bond Wolfe was empty ("Properties coming soon") but that is one house. This asks
all four, using each one's upcoming-auction catalogue rather than past results.

  python live_all.py --outcodes ST15 ST16 ST17 ST18 ST19 ST20 ST21
"""

import argparse
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

import scrape_allsop as AL
import scrape_emson as EM
import scrape_sdl as SDL

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
           "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
           "Accept-Language": "en-GB,en;q=0.9"}
NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat", "O": "Land/comm"}


def outcode(pc):
    p = (pc or "").split()
    return p[0] if len(p) == 2 else ""


def sdl_upcoming(session, outcodes):
    """SDL lists future auctions on its main auctions page."""
    out = []
    try:
        html = session.get("https://www.sdlauctions.co.uk/property-auctions/",
                           timeout=45).text
        time.sleep(3)
    except requests.RequestException as e:
        print(f"  ! SDL index: {e}", file=sys.stderr)
        return out
    events = {}
    for m in re.finditer(r"/auction/(\d+)/([a-z0-9\-]*?(\d{4}-\d{2}-\d{2}))/", html):
        events[m.group(1)] = m.group(3)
    today = time.strftime("%Y-%m-%d")
    future = {a: d for a, d in events.items() if d >= today}
    print(f"  SDL: {len(future)} upcoming auction(s) {sorted(future.values())}")
    for aid, date in sorted(future.items(), key=lambda x: x[1]):
        try:
            lots = SDL.parse_cards(SDL.fetch_lots_html(aid), date)
        except Exception as e:
            print(f"  ! SDL auction {aid}: {e}", file=sys.stderr)
            continue
        hits = [l for l in lots if outcode(l.postcode) in outcodes]
        print(f"    auction {aid} ({date}): {len(lots)} lots, {len(hits)} in area")
        out += [{"house": "SDL", "date": date, "type": l.property_type,
                 "beds": l.bedrooms, "postcode": l.postcode, "status": l.status,
                 "guide": l.guide_price, "guide_max": l.guide_price_max,
                 "address": l.address_raw, "url": l.lot_url} for l in hits]
    return out


def allsop_upcoming(session, outcodes):
    out = []
    try:
        html = session.get("https://www.allsop.co.uk/auctions/future-auction-dates/",
                           timeout=45).text
        time.sleep(3)
    except requests.RequestException as e:
        print(f"  ! Allsop index: {e}", file=sys.stderr)
        return out
    ids = list(dict.fromkeys(re.findall(r"auction_id=([0-9a-f\-]{16,})", html)))
    print(f"  Allsop: {len(ids)} upcoming auction id(s)")
    for aid in ids[:4]:
        try:
            lots = AL.fetch_auction(session, aid)
        except Exception as e:
            print(f"  ! Allsop {aid[:8]}: {e}", file=sys.stderr)
            continue
        hits = [l for l in lots if outcode(l.postcode) in outcodes]
        print(f"    {aid[:8]}: {len(lots)} lots, {len(hits)} in area")
        out += [{"house": "Allsop", "date": l.auction_date, "type": l.property_type,
                 "beds": l.bedrooms, "postcode": l.postcode, "status": l.status,
                 "guide": l.guide_price, "guide_max": l.guide_price_max,
                 "address": l.address_raw, "url": l.lot_url} for l in hits]
    return out


def emson_current(session, outcodes):
    """Clive Emson's current catalogue lives on /properties/."""
    out = []
    try:
        html = session.get("https://www.cliveemson.co.uk/properties/", timeout=60).text
        time.sleep(10)          # their robots.txt asks for Crawl-Delay: 10
    except requests.RequestException as e:
        print(f"  ! Clive Emson: {e}", file=sys.stderr)
        return out
    lots, coords = EM.parse_results(html, "current", None)
    print(f"  Clive Emson: {len(lots)} lots in the current catalogue")
    if lots:
        EM.reverse_geocode(session, lots, coords)
    hits = [l for l in lots if outcode(l.postcode) in outcodes]
    print(f"    {len(hits)} in area")
    out += [{"house": "Clive Emson", "date": l.auction_date, "type": l.property_type,
             "beds": None, "postcode": l.postcode, "status": l.status,
             "guide": None, "guide_max": None,
             "address": l.address_raw, "url": l.lot_url} for l in hits]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outcodes", nargs="+",
                    default=["ST15", "ST16", "ST17", "ST18", "ST19", "ST20", "ST21"])
    args = ap.parse_args()
    want = set(args.outcodes)

    s = requests.Session()
    s.headers.update(HEADERS)
    print(f"looking for live lots in {'/'.join(sorted(want))}\n")

    found = []
    found += sdl_upcoming(s, want)
    found += allsop_upcoming(s, want)
    s.headers.update({"Accept": "text/html"})
    found += emson_current(s, want)

    print("\n" + "=" * 70)
    if not found:
        print("  NOTHING LIVE IN THIS AREA RIGHT NOW")
        print("  Auction stock exists only while a catalogue is open. Re-run when")
        print("  the next catalogues publish, usually 3-4 weeks before sale day.")
    else:
        print(f"  {len(found)} LIVE LOT(S)")
        for l in sorted(found, key=lambda x: (x["date"] or "", x["address"])):
            g = ""
            if l["guide"]:
                g = f"guide £{l['guide']:,}"
                if l["guide_max"]:
                    g += f" - £{l['guide_max']:,}"
            print(f"\n  {l['house']}  {l['date']}  {NAME.get(l['type'], '?')}  "
                  f"{l['postcode']}  {g}")
            print(f"    {l['address'][:66]}")
            print(f"    {l['url']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
