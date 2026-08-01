"""Read the new EPC service's API technical documentation."""
import re
import requests
from bs4 import BeautifulSoup

URL = ("https://get-energy-performance-data.communities.gov.uk/"
       "api-technical-documentation")
H = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
     "Accept": "text/html,application/xhtml+xml"}

r = requests.get(URL, headers=H, timeout=45)
print("status:", r.status_code, "len:", len(r.text), "final:", r.url)
soup = BeautifulSoup(r.text, "html.parser")
text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
print("chars of rendered text:", len(text))

# Strip the GOV.UK cookie banner boilerplate so the real content is visible.
cut = text.find("Skip to main content")
body = text[cut + 20:] if cut != -1 else text
print("\n===== documentation text =====")
print(body[:5000])

print("\n===== code / endpoint samples =====")
for pre in soup.find_all(["code", "pre"])[:25]:
    t = re.sub(r"\s+", " ", pre.get_text(" ", strip=True))
    if t:
        print("  ", t[:180])

print("\n===== links =====")
for a in soup.find_all("a", href=True):
    h = a["href"]
    if re.search(r"api|token|auth|swagger|openapi|docs|key", h, re.I):
        print(f"   {h[:110]:112} {a.get_text(' ', strip=True)[:44]}")
