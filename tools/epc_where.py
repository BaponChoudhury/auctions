"""Where did the EPC API go? Read what the site now says."""
import re
import requests
from bs4 import BeautifulSoup

r = requests.get("https://epc.opendatacommunities.org/api/v1/domestic/search",
                 headers={"User-Agent": "AuctionResearchBot/0.1 "
                                        "(contact: mailahb2017@gmail.com)"},
                 timeout=30)
soup = BeautifulSoup(r.text, "html.parser")
title = soup.find("title")
print("title:", title.get_text(strip=True) if title else "")
text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
print("\npage text (first 900 chars):\n", text[:900])

print("\n--- outbound links mentioning api / data / moved ---")
seen = set()
for a in soup.find_all("a", href=True):
    h = a["href"]
    if re.search(r"api|data|moved|new|gov\.uk|service", h, re.I) and h not in seen:
        seen.add(h)
        print(f"  {h[:100]:102} {a.get_text(' ', strip=True)[:40]}")
