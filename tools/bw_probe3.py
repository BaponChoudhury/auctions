"""Read how search.js initialises its params, then retry get_properties."""
import json, re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
           "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
LIST = "https://www.bondwolfe.com/auctions/properties/"

s = requests.Session(); s.headers.update(HEADERS)
js = s.get("https://www.bondwolfe.com/wp-content/themes/bwa/properties/js/search.js?ver=1.12",
           timeout=30).text

print("--- how each var is read ---")
for var in ("page", "total_pages", "postsperpage", "auction", "status", "orderby", "get_map"):
    m = re.search(rf"var {var}\s*=\s*([^;]+);", js)
    print(f"  {var:14} = {m.group(1).strip() if m else '?'}")

page_html = s.get(LIST, timeout=30).text
cfg = json.loads(re.search(r"tjdPropertyAjax\s*=\s*(\{.*?\})\s*;", page_html, re.S).group(1))

# The hidden inputs the JS reads its defaults from.
soup = BeautifulSoup(page_html, "html.parser")
defaults = {}
for inp in soup.select("input, select"):
    n = inp.get("name")
    if n in ("page", "total_pages", "postsperpage", "auction", "status", "orderby",
             "location", "radius", "type", "minprice", "maxprice"):
        defaults[n] = inp.get("value", "")
print("\n--- form defaults on the page ---")
print(defaults)

base = {"action": "get_properties", "page": "1", "total_pages": "0", "postsperpage": "24",
        "orderby": "", "location": "", "radius": "", "type": "", "minprice": "",
        "maxprice": "", "auction": "", "status": "", "get_map": "false",
        "security": cfg["ajaxnonce"]}
base.update({k: v for k, v in defaults.items() if v})

for label, extra in [("page defaults", {}),
                     ("status=sold", {"status": "sold"}),
                     ("postsperpage=100", {"postsperpage": "100"}),
                     ("get_map=true", {"get_map": "true"})]:
    d = dict(base, **extra)
    r = s.post(cfg["ajaxurl"], data=d,
               headers={"X-Requested-With": "XMLHttpRequest", "Referer": LIST}, timeout=45)
    try:
        j = r.json()
    except ValueError:
        print(f"\n{label}: non-JSON {r.text[:160]}"); continue
    html = (j.get("data") or {}).get("html", "") or ""
    n = len(BeautifulSoup(html, "html.parser").select("[class*=card], article"))
    print(f"\n{label}: success={j.get('success')} htmlLen={len(html)} cards={n}")
    if not j.get("success"):
        print("   body:", json.dumps(j)[:200])
    elif html:
        open("bw_lots.html", "w", encoding="utf-8").write(html)
        print("   saved bw_lots.html")
        break
