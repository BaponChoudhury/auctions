"""How much data do we hold for specific places?"""
import collections, json, sys
sys.path.insert(0, "../src")
from geo import load_cache

geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    lots += [json.loads(l) for l in open(f"../data/{p}.jsonl", encoding="utf-8") if l.strip()]

for l in lots:
    g = geo.get(l.get("postcode") or "") or {}
    l["district"] = g.get("admin_district")

WANT = ["Stafford", "Birmingham", "Stoke-on-Trent"]
print(f"{'district':22} {'lots':>6} {'sold':>6} {'priced':>7} {'sectors':>8}")
for d in WANT:
    sub = [l for l in lots if l["district"] == d]
    sold = [l for l in sub if l["hammer_price"]]
    sect = len({l["postcode_sector"] for l in sub if l["postcode_sector"]})
    print(f"{d:22} {len(sub):6,} {len(sold):6,} "
          f"{100*len(sold)//max(len(sub),1):6}% {sect:8}")

print("\nnearby districts that might matter for Stafford:")
for d, n in collections.Counter(
        l["district"] for l in lots if l["district"] and
        any(k in l["district"] for k in
            ("Stafford", "Newcastle", "Lichfield", "Cannock", "Stone",
             "South Staffordshire", "East Staffordshire"))).most_common():
    sold = sum(1 for l in lots if l["district"] == d and l["hammer_price"])
    print(f"  {d:26} {n:5,} lots, {sold:4,} sold")
