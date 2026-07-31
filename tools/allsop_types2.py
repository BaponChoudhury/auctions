"""Check type labels on a RESIDENTIAL Allsop auction (the big catalogues)."""
import collections, re, sys
import requests

sys.path.insert(0, "../src")
from scrape_allsop import property_type

BASE = "https://www.allsop.co.uk"
S = requests.Session()
S.headers.update({"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
                  "Accept": "application/json"})
html = S.get(f"{BASE}/auctions/past-auction-results/",
             headers={"Accept": "text/html"}, timeout=30).text
ids = list(dict.fromkeys(re.findall(r"auction_id=([0-9a-f\-]{16,})", html)))
# The big residential catalogues sit after the commercial ones on the index.
AID = sys.argv[1] if len(sys.argv) > 1 else ids[5]
print("auction:", AID)

payload = S.get(f"{BASE}/api/search", params={"auction_id": AID, "size": 500},
                timeout=60).json()
data = payload.get("data")
res = data.get("results", []) if isinstance(data, dict) else (data or [])
lots = [l for l in res if l.get("allsop_lotid")]
print(f"lots: {len(lots)}  catalogue_type={ {l.get('catalogue_type') for l in lots} }")

unmapped = collections.Counter()
n_mapped = 0
for lot in lots:
    if property_type(lot):
        n_mapped += 1
        continue
    labels = []
    for k in ("residential_property_types", "resi_property_types",
              "commercial_property_types", "comm_property_types",
              "allsop_propertytype", "property_types"):
        v = lot.get(k)
        if isinstance(v, list):
            labels += [str(x) for x in v]
        elif isinstance(v, str) and v:
            labels.append(v)
    unmapped[" | ".join(sorted(set(labels))) or "(NO type labels)"] += 1

print(f"mapped {n_mapped}/{len(lots)}  ({100*n_mapped//len(lots)}%)\n")
print("unmapped labels:")
for label, n in unmapped.most_common(20):
    print(f"  {n:4}  {label[:80]}")

# If labels are missing entirely, is the type in the byline instead?
missing = [l for l in lots if not property_type(l)]
if missing:
    print("\nbylines of unmapped lots (is the type in the text?):")
    for l in missing[:6]:
        print("   ", (l.get("main_byline") or l.get("allsop_propertybyline") or "")[:82])
