"""What are the current EPC data access options and API endpoint?"""
import re
import requests
from bs4 import BeautifulSoup

BASE = "https://epc.opendatacommunities.org"
H = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}

for path in ("/data-access-options", "/docs/api", "/docs/api/domestic"):
    r = requests.get(BASE + path, headers=H, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    print(f"\n=== {path}  ({r.status_code}, {len(text)} chars)")
    print(text[:1100])
    links = {a["href"] for a in soup.find_all("a", href=True)
             if re.search(r"api|download|bulk|docs", a["href"], re.I)}
    if links:
        print("  links:", sorted(links)[:12])
