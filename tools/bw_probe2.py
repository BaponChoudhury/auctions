"""Extract Bond Wolfe's ajax nonce + param list, then call get_properties."""
import json, re, sys
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
           "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
LIST = "https://www.bondwolfe.com/auctions/properties/"

s = requests.Session()
s.headers.update(HEADERS)

js = s.get("https://www.bondwolfe.com/wp-content/themes/bwa/properties/js/search.js?ver=1.12",
           timeout=30).text
m = re.search(r"var data = \{(.*?)\n\t\t\}", js, re.S)
print("--- ajax payload keys ---")
print(m.group(1).strip() if m else "not found")

page = s.get(LIST, timeout=30).text
loc = re.search(r"tjdPropertyAjax\s*=\s*(\{.*?\})\s*;", page, re.S)
print("\n--- localized object ---")
print(loc.group(1) if loc else "NOT FOUND")
if not loc:
    sys.exit(1)
cfg = json.loads(loc.group(1))

# What does the page think it is filtering on?
for name in ("auction", "status", "postsperpage", "total_pages"):
    for mm in re.finditer(rf'name=[\'"]{name}[\'"][^>]*', page):
        print(f"  input {name}: {mm.group(0)[:150]}")
        break

data = {"action": "get_properties", "page": 1, "total_pages": 1, "postsperpage": 24,
        "orderby": "", "location": "", "radius": "", "type": "", "minprice": "",
        "maxprice": "", "beds": "", "status": "", "get_map": "false",
        "security": cfg["ajaxnonce"]}
r = s.post(cfg["ajaxurl"], data=data,
           headers={"X-Requested-With": "XMLHttpRequest", "Referer": LIST}, timeout=45)
print("\n--- ajax response ---")
print("status:", r.status_code, "len:", len(r.text), "ctype:", r.headers.get("content-type"))
try:
    j = r.json()
except ValueError:
    print(r.text[:400]); sys.exit(1)
print("success:", j.get("success"), "keys:", list((j.get("data") or {}).keys()))
html = (j.get("data") or {}).get("html", "")
open("bw_lots.html", "w", encoding="utf-8").write(html)
soup = BeautifulSoup(html, "html.parser")
for sel in ("[class*=card]", "[class*=propert]", "article", "li", "[class*=result]"):
    found = soup.select(sel)
    if found:
        print(f"  {sel:20} {len(found):4} {sorted({' '.join(e.get('class') or []) for e in found})[:3]}")
txt = soup.get_text(" ", strip=True)
for cue in ("Sold", "Guide", "Withdrawn", "Unsold", "Lot"):
    print(f"  text '{cue}': {txt.count(cue)}")
