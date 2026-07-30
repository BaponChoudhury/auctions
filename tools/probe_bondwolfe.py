"""Locate Bond Wolfe's auction results pages and inspect their markup."""
import re, sys, time
import requests
from bs4 import BeautifulSoup

BASE = "https://www.bondwolfe.com"
HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
           "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-GB,en;q=0.9"}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    time.sleep(2)
    return r


if len(sys.argv) > 1:
    r = get(sys.argv[1])
    print("status:", r.status_code, "len:", len(r.text))
    open("bw_probe.html", "w", encoding="utf-8").write(r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    for sel in ("[class*=lot]", "[class*=result]", "[class*=propert]", "[class*=card]",
                "article", "[class*=auction]"):
        found = soup.select(sel)
        if found:
            classes = {" ".join(e.get("class") or []) for e in found}
            print(f"  {sel:22} {len(found):4}  {list(classes)[:4]}")
    txt = soup.get_text(" ", strip=True)
    for cue in ("Sold", "Guide", "Withdrawn", "Unsold", "results"):
        print(f"  text '{cue}': {txt.count(cue)}")
    sys.exit()

r = get(BASE)
soup = BeautifulSoup(r.text, "html.parser")
seen = set()
for a in soup.find_all("a", href=True):
    href, label = a["href"], a.get_text(" ", strip=True)[:44]
    if re.search(r"result|auction|catalog|propert", href, re.I):
        full = href if href.startswith("http") else BASE + href
        if full not in seen:
            seen.add(full)
            print(f"{full:78} {label}")
