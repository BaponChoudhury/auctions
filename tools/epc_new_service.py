"""Confirm the replacement EPC service and what access it requires."""
import re
import requests
from bs4 import BeautifulSoup

H = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
for url in ("https://get-energy-performance-data.communities.gov.uk/",
            "https://epc.opendatacommunities.org/"):
    try:
        r = requests.get(url, headers=H, timeout=30, allow_redirects=True)
    except requests.RequestException as e:
        print(f"{url} -> ERR {type(e).__name__}")
        continue
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    print(f"\n=== {url}\n    {r.status_code}, final={r.url}")
    print("   ", text[:520])
    signin = [a["href"] for a in soup.find_all("a", href=True)
              if re.search(r"sign-?in|login|one-?login|account|download", a["href"], re.I)]
    if signin:
        print("    access links:", sorted(set(signin))[:6])
