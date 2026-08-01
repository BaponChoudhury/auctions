"""Is any auction catalogue actually open right now?
Checks Bond Wolfe (unfiltered) and SDL's upcoming auctions."""
import json, re, sys, time
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, "../src")
from scrape_bondwolfe import BASE as BW, HEADERS, NONCE_RE, SELECTORS

s = requests.Session(); s.headers.update(HEADERS)

print("=== Bond Wolfe: any lots at all (no location filter) ===")
html = s.get(f"{BW}/auctions/properties/", timeout=45).text
time.sleep(3)
cfg = json.loads(NONCE_RE.search(html).group(1))
r = s.post(cfg["ajaxurl"],
           data={"action": "get_properties", "page": "1", "total_pages": "1",
                 "postsperpage": "96", "orderby": "", "location": "", "radius": "",
                 "type": "", "minprice": "", "maxprice": "", "auction": "",
                 "status": "", "get_map": "false", "security": cfg["ajaxnonce"]},
           headers={"X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{BW}/auctions/properties/"}, timeout=60)
time.sleep(3)
j = r.json()
h = (j.get("data") or {}).get("html") or ""
cards = BeautifulSoup(h, "html.parser").select(SELECTORS["card"])
print(f"  success={j.get('success')}  cards={len(cards)}")
if not cards:
    print("  message:", re.sub(r"<[^>]+>", " ", h).strip()[:120])

print("\n=== Bond Wolfe: next auction date advertised ===")
up = s.get(f"{BW}/property-auctions-west-midlands/upcoming-property-auctions/",
           timeout=45).text
time.sleep(3)
txt = re.sub(r"\s+", " ", BeautifulSoup(up, "html.parser").get_text(" ", strip=True))
for m in re.finditer(r"((?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+\d{1,2}\w{0,2}\s+"
                     r"[A-Z][a-z]+\s+\d{4})", txt):
    print("  ", m.group(1))

print("\n=== SDL: upcoming auctions ===")
sdl = s.get("https://www.sdlauctions.co.uk/property-auctions/", timeout=45,
            headers={**HEADERS, "Accept": "text/html"})
time.sleep(3)
if sdl.status_code == 200:
    t = re.sub(r"\s+", " ", BeautifulSoup(sdl.text, "html.parser").get_text(" ", strip=True))
    for m in list(re.finditer(r"(\d{1,2}(?:st|nd|rd|th)\s+[A-Z][a-z]+\s+20\d\d)", t))[:6]:
        print("  ", m.group(1))
    ids = sorted(set(re.findall(r"/auction/(\d+)/[a-z0-9\-]*?(\d{4}-\d{2}-\d{2})", sdl.text)),
                 key=lambda x: x[1], reverse=True)[:5]
    for a, d in ids:
        print(f"   auction {a} -> {d}")
else:
    print("  SDL returned", sdl.status_code)
