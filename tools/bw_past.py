"""What does Bond Wolfe actually publish on its past-auctions page?"""
import re, requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
url = "https://www.bondwolfe.com/property-auctions-west-midlands/past-property-auctions/"
html = requests.get(url, headers=HEADERS, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

main = soup.select_one("main, .main, article, .content") or soup
text = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
print("--- page copy (first 700 chars) ---")
print(text[:700])

print("\n--- links that look like results/catalogues ---")
seen = set()
for a in soup.find_all("a", href=True):
    h = a["href"]
    if re.search(r"result|catalog|pdf|past|archive|\d{4}", h, re.I):
        if h not in seen:
            seen.add(h)
            print(f"  {h[:100]:100} {a.get_text(' ', strip=True)[:40]}")
print(f"\n({len(seen)} candidate links)")
