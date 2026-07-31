"""Extract Clive Emson's per-auction results links from /future/results/."""
import re
from bs4 import BeautifulSoup

html = open("emson_probe.html", encoding="utf-8").read()
soup = BeautifulSoup(html, "html.parser")

for block in soup.select(".paraBlock"):
    year = block.find(["h2"])
    lst = block.select_one(".auctionResultsList")
    if not lst:
        continue
    print(f"\n=== {year.get_text(strip=True) if year else '?'}")
    for li in lst.select("li"):
        label = re.sub(r"\s+", " ", li.get_text(" ", strip=True))[:60]
        hrefs = [a.get("href") for a in li.select("a[href]")]
        btns = [b.get("onclick") or b.get("data-href") or b.get("formaction")
                for b in li.select("button")]
        print(f"  {label:62} {hrefs or btns}")

# Anything else that looks like a results endpoint?
print("\n--- pdf / download / results links anywhere on the page ---")
for a in soup.find_all(["a", "button"]):
    blob = " ".join(str(a.get(k) or "") for k in ("href", "onclick", "data-href", "formaction"))
    if re.search(r"result|pdf|download|\.csv|auction=", blob, re.I):
        print("   ", re.sub(r"\s+", " ", blob)[:130])
