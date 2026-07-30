"""Call get_properties for a specific past Bond Wolfe auction id."""
import json, re, sys
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
           "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
AID = sys.argv[1] if len(sys.argv) > 1 else "3450"
EVENT = f"https://www.bondwolfe.com/auction/{AID}/"

s = requests.Session(); s.headers.update(HEADERS)
page = s.get(EVENT, timeout=30).text
cfg = json.loads(re.search(r"tjdPropertyAjax\s*=\s*(\{.*?\})\s*;", page, re.S).group(1))

for pp in ("All", "96", "24"):
    d = {"action": "get_properties", "page": "1", "total_pages": "1", "postsperpage": pp,
         "orderby": "", "location": "", "radius": "", "type": "", "minprice": "",
         "maxprice": "", "auction": AID, "status": "", "get_map": "false",
         "security": cfg["ajaxnonce"]}
    r = s.post(cfg["ajaxurl"], data=d,
               headers={"X-Requested-With": "XMLHttpRequest", "Referer": EVENT}, timeout=60)
    try:
        j = r.json()
    except ValueError:
        print(f"perpage={pp:4} non-JSON ({r.status_code}, {len(r.text)}b): {r.text[:120]!r}")
        continue
    html = (j.get("data") or {}).get("html", "") or ""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("[class*=card], article, [class*=property-item]")
    print(f"perpage={pp:4} success={j.get('success')} len={len(html):7} cards={len(cards)}")
    if j.get("success") and cards:
        open("bw_lots.html", "w", encoding="utf-8").write(html)
        classes = sorted({" ".join(e.get("class") or []) for e in cards})
        print("  card classes:", classes[:3])
        txt = re.sub(r"\s+", " ", cards[0].get_text(" ", strip=True))
        print("  first card:", txt[:220])
        for cue in ("Sold", "Guide", "Withdrawn", "Unsold", "Lot "):
            print(f"    '{cue}': {soup.get_text(' ').count(cue)}")
        break
