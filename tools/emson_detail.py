"""Does a Clive Emson lot detail page carry a full address / postcode?"""
import re, time
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
url = "https://www.cliveemson.co.uk/properties/259/1/"
r = requests.get(url, headers=HEADERS, timeout=45)
time.sleep(10)
html = r.text
print("status:", r.status_code, "len:", len(html))

pcs = re.findall(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", html)
print("postcode-shaped strings:", len(pcs), sorted(set(pcs))[:6])

soup = BeautifulSoup(html, "html.parser")
for sel in ("h1", "h2", ".LotHeading", ".LotLocation", "[class*=address]",
            "[class*=Address]", "[class*=lotDetail]", "[class*=guide]"):
    for e in soup.select(sel)[:3]:
        t = re.sub(r"\s+", " ", e.get_text(" ", strip=True))[:110]
        if t:
            print(f"  {sel:20} {t}")

text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
for kw in ("Guide", "Sold", "Freehold", "Tenure"):
    m = re.search(rf"{kw}[^.]{{0,90}}", text, re.I)
    if m:
        print(f"  [{kw}] {m.group(0)[:110]}")
print("\nfirst 400 chars of rendered text:\n ", text[:400])
