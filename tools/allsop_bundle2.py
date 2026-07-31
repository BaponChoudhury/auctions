"""Find the request Allsop's SPA makes to list lots for an auction."""
import re, requests

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
URL = ("https://assets.allsop-cdn.co.uk/build/js/react/packages/platform/"
       "frontend/bundle-1aef6e8e37.js")
js = requests.get(URL, headers=HEADERS, timeout=60).text

for term in ("auction_id", "auctionId", "/api/lots", "propertySearch", "property-search"):
    idxs = [m.start() for m in re.finditer(re.escape(term), js)]
    print(f"\n=== {term}: {len(idxs)} hits")
    for i in idxs[:4]:
        print("   ...", re.sub(r"\s+", " ", js[max(0, i-220):i+220]), "...")
