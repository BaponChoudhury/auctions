"""Compare the date we derive from auction_date against the date Allsop publishes."""
import re, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, "../src")
from scrape_allsop import auction_date as our_date

BASE = "https://www.allsop.co.uk"
S = requests.Session()
S.headers.update({"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"})

html = S.get(f"{BASE}/auctions/past-auction-results/", timeout=30).text
soup = BeautifulSoup(html, "html.parser")

# Each <li> holds the published date text and the View Results link.
published = {}
for li in soup.select("li"):
    a = li.select_one("a[href*='auction_id=']")
    if not a:
        continue
    aid = re.search(r"auction_id=([0-9a-f\-]+)", a["href"]).group(1)
    txt = re.sub(r"\s+", " ", li.get_text(" ", strip=True))
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]+)\s+(\d{4})", txt)
    published[aid] = m.group(0) if m else txt[:60]

print(f"{'auction':10} {'published on site':22} {'utc date':12} {'europe/london':12}")
for aid, pub in list(published.items())[:8]:
    d = S.get(f"{BASE}/api/search", params={"auction_id": aid, "size": 1}, timeout=60).json()
    res = (d.get("data") or {}).get("results") or []
    lot = next((x for x in res if x.get("auction_date")), None)
    if not lot:
        print(f"{aid[:8]:10} {pub:22} (no lots)")
        continue
    ms = int(lot["auction_date"])
    utc = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    lon = datetime.fromtimestamp(ms / 1000, tz=ZoneInfo("Europe/London")).date().isoformat()
    flag = "" if lon in pub.replace(" ", "") or True else ""
    print(f"{aid[:8]:10} {pub:22} {utc:12} {lon:12} {'MISMATCH' if utc != lon else ''}")
