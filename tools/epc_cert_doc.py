"""Does the certificate endpoint return floor area? That is the feature we want."""
import re
import requests
from bs4 import BeautifulSoup

BASE = "https://get-energy-performance-data.communities.gov.uk"
H = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}

r = requests.get(f"{BASE}/api-technical-documentation/fetch-certificate-data",
                 headers=H, timeout=45)
soup = BeautifulSoup(r.text, "html.parser")
text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
cut = text.find("Fetch certificate data", 200)
body = text[cut:] if cut != -1 else text
print(body[:4500])

print("\n--- does the payload mention floor area / age? ---")
for kw in ("floor", "area", "totalFloorArea", "age", "constructionAge", "builtForm",
           "propertyType", "tenure"):
    for m in re.finditer(kw, r.text, re.I):
        s = max(0, m.start() - 90)
        frag = re.sub(r"<[^>]+>", "", r.text[s:m.end() + 90])
        print(f"  [{kw}] ...{re.sub(r'\\s+', ' ', frag).strip()[:150]}...")
        break
