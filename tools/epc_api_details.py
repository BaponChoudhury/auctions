"""Auth mechanism and the domestic search endpoint for the new EPC API."""
import re
import requests
from bs4 import BeautifulSoup

BASE = "https://get-energy-performance-data.communities.gov.uk"
H = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}

for path in ("/api-technical-documentation/making-a-request",
             "/api-technical-documentation/search-certificates/domestic"):
    r = requests.get(BASE + path, headers=H, timeout=45)
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    cut = text.find("Skip to main content")
    body = text[cut + 20:] if cut != -1 else text
    print(f"\n{'='*72}\n=== {path}  ({r.status_code})\n{'='*72}")
    print(body[:3800])
    codes = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))
             for c in soup.find_all(["code", "pre"])]
    codes = [c for c in codes if c]
    if codes:
        print("\n--- code samples ---")
        for c in codes[:20]:
            print("   ", c[:200])
    tables = soup.find_all("table")
    for t in tables[:2]:
        print("\n--- table ---")
        for tr in t.find_all("tr")[:16]:
            cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True))[:44]
                     for td in tr.find_all(["th", "td"])]
            if cells:
                print("   ", " | ".join(cells))
