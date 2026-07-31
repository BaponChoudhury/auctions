"""Find Clive Emson's past results and see how lots are served.
Their robots.txt asks for Crawl-Delay: 10, so this sleeps 10s between requests."""
import re, sys, time
import requests
from bs4 import BeautifulSoup

BASE = "https://www.cliveemson.co.uk"
HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
DELAY = 10.0


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=45)
    time.sleep(DELAY)
    return r


if len(sys.argv) > 1:
    r = get(sys.argv[1])
    print("status:", r.status_code, "len:", len(r.text))
    open("emson_probe.html", "w", encoding="utf-8").write(r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    for sel in ("[class*=lot]", "[class*=result]", "[class*=propert]", "[class*=card]",
                "article", "table", "[class*=auction]"):
        found = soup.select(sel)
        if found:
            cls = sorted({" ".join(e.get("class") or []) for e in found})[:3]
            print(f"  {sel:20} {len(found):4} {cls}")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    for cue in ("Sold", "Guide", "Withdrawn", "Unsold", "Lot "):
        print(f"  text '{cue}': {len(re.findall(rf'\\b{cue}', text, re.I))}")
    print(f"  £ amounts: {len(re.findall(r'£[\\d,]{4,}', r.text))}")
    print("  rendered text chars:", len(text))
    sys.exit()

r = get(BASE)
soup = BeautifulSoup(r.text, "html.parser")
seen = set()
for a in soup.find_all("a", href=True):
    h = a["href"]
    if re.search(r"result|auction|catalog|lot|propert|archive", h, re.I):
        full = h if h.startswith("http") else BASE + "/" + h.lstrip("/")
        if full not in seen:
            seen.add(full)
            print(f"{full[:86]:88} {a.get_text(' ', strip=True)[:38]}")
