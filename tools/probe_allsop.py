"""Find Allsop's auction results pages and work out how lots are served."""
import re, sys, time
import requests
from bs4 import BeautifulSoup

BASE = "https://www.allsop.co.uk"
HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
           "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-GB,en;q=0.9"}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    time.sleep(2)
    return r


if len(sys.argv) > 1:
    r = get(sys.argv[1])
    print("status:", r.status_code, "len:", len(r.text))
    open("allsop_probe.html", "w", encoding="utf-8").write(r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    for sel in ("[class*=lot]", "[class*=result]", "[class*=propert]", "[class*=card]",
                "[class*=auction]", "article", "table"):
        found = soup.select(sel)
        if found:
            cls = sorted({" ".join(e.get("class") or []) for e in found})[:3]
            print(f"  {sel:20} {len(found):4} {cls}")
    txt = soup.get_text(" ", strip=True)
    for cue in ("Sold", "Guide", "Withdrawn", "Unsold", "Lot "):
        print(f"  text '{cue}': {txt.count(cue)}")
    print("\n  scripts:")
    for s in soup.find_all("script", src=True)[:14]:
        print("   ", s["src"][:110])
    print("\n  next/nuxt data present:",
          bool(re.search(r"__NEXT_DATA__|__NUXT__|window\.__", r.text)))
    sys.exit()

r = get(BASE)
soup = BeautifulSoup(r.text, "html.parser")
seen = set()
for a in soup.find_all("a", href=True):
    href = a["href"]
    if re.search(r"auction|result|catalog|lot", href, re.I):
        full = href if href.startswith("http") else BASE + href
        if full not in seen:
            seen.add(full)
            print(f"{full:82} {a.get_text(' ', strip=True)[:40]}")
