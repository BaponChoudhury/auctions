"""Merge multiple sources and check they compose: keys, overlap, re-offers."""
import collections, json, statistics, sys

rows = []
for path in sys.argv[1:]:
    rows += [json.loads(l) for l in open(path, encoding="utf-8")]

by_src = collections.Counter(r["source"] for r in rows)
print(f"lots: {len(rows)}  from {len(by_src)} sources -> {dict(by_src)}")

print("\nper-source field coverage (%):")
fields = ("postcode", "property_key", "property_type", "guide_price", "hammer_price",
          "description", "bedrooms")
print(f"  {'source':11}" + "".join(f"{f[:12]:>14}" for f in fields))
for src in by_src:
    sub = [r for r in rows if r["source"] == src]
    line = f"  {src:11}"
    for f in fields:
        n = sum(1 for r in sub if r.get(f) not in (None, "", 0))
        line += f"{100*n//len(sub):>13}%"
    print(line)

print("\nstatus vocabulary agrees across sources:")
for src in by_src:
    sub = [r for r in rows if r["source"] == src]
    print(f"  {src:11}", dict(collections.Counter(r["status"] for r in sub).most_common()))

# The point of a shared property_key: does the same property appear in BOTH?
keys = collections.defaultdict(set)
for r in rows:
    if r["property_key"]:
        keys[r["property_key"]].add(r["source"])
cross = {k: v for k, v in keys.items() if len(v) > 1}
print(f"\nproperties seen by more than one auction house: {len(cross)}")
for k in list(cross)[:5]:
    ex = next(r for r in rows if r["property_key"] == k)
    print(f"  {k:22} {ex['address_raw'][:50]}")

sold = [r for r in rows if r["hammer_price"]]
print(f"\nsold with a published price: {len(sold)}/{len(rows)} "
      f"({100*len(sold)//len(rows)}%)")
print(f"  median hammer £{int(statistics.median(r['hammer_price'] for r in sold)):,}")
print(f"  total raised  £{sum(r['hammer_price'] for r in sold):,}")

# Overlapping geography is what makes cross-source comps meaningful.
sect = collections.defaultdict(set)
for r in rows:
    if r["postcode_sector"]:
        sect[r["postcode_sector"]].add(r["source"])
shared = [s for s, v in sect.items() if len(v) > 1]
print(f"\npostcode sectors covered by both sources: {len(shared)} "
      f"(of {len(sect)} total)")
