"""Which Allsop type labels are we failing to map to a PPD code?"""
import collections, json, sys
import requests

sys.path.insert(0, "../src")
from scrape_allsop import property_type

BASE = "https://www.allsop.co.uk"
S = requests.Session()
S.headers.update({"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
                  "Accept": "application/json"})

unmapped = collections.Counter()
mapped = collections.Counter()
for aid in ("d21a81d6-0d95-11f1-9a3f-0242ac110002",):
    pass

# Use the saved corpus instead of re-requesting: re-derive from raw is not
# possible, so re-fetch two auctions' raw JSON.
import re
html = S.get(f"{BASE}/auctions/past-auction-results/", timeout=30).text
ids = list(dict.fromkeys(re.findall(r"auction_id=([0-9a-f\-]{16,})", html)))[:3]
for aid in ids:
    res = S.get(f"{BASE}/api/search", params={"auction_id": aid, "size": 500},
                timeout=60).json()["data"]["results"]
    for lot in res:
        if not lot.get("allsop_lotid"):
            continue
        code = property_type(lot)
        labels = []
        for k in ("residential_property_types", "commercial_property_types",
                  "allsop_propertytype", "property_types"):
            v = lot.get(k)
            if isinstance(v, list):
                labels += [str(x) for x in v]
            elif isinstance(v, str) and v:
                labels.append(v)
        key = " | ".join(sorted(set(labels))) or "(no type labels at all)"
        (mapped if code else unmapped)[key] += 1

print("UNMAPPED labels (no PPD code assigned):")
for label, n in unmapped.most_common(20):
    print(f"  {n:4}  {label[:88]}")
print("\nmapped, for contrast:")
for label, n in mapped.most_common(8):
    print(f"  {n:4}  {label[:88]}")
