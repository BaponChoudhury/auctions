"""Summarise the full scraped corpus and flag suspicious events."""
import collections, json, statistics, sys

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
print(f"lots: {len(rows)}")
print("status:", dict(collections.Counter(r["status"] for r in rows).most_common()))

byev = collections.defaultdict(list)
for r in rows:
    byev[r["auction_date"]].append(r)
print(f"\nevents: {len(byev)}")

thin = sorted((d, len(v)) for d, v in byev.items() if len(v) < 20)
if thin:
    print("thin events (<20 lots) — check these are real, not scrape gaps:")
    for d, n in thin:
        print(f"  {d}: {n}")

sold = [r for r in rows if r["hammer_price"] and r["guide_price"] and r["guide_price"] >= 1000]
up = [(r["hammer_price"] - r["guide_price"]) / r["guide_price"] * 100 for r in sold]
print(f"\nsold with usable guide: {len(sold)}")
print(f"  median guide  £{int(statistics.median(r['guide_price'] for r in sold)):,}")
print(f"  median hammer £{int(statistics.median(r['hammer_price'] for r in sold)):,}")
print(f"  median uplift {statistics.median(up):.0f}%")
print(f"  over guide    {sum(1 for u in up if u > 0)}/{len(up)}")
print(f"  total raised  £{sum(r['hammer_price'] for r in rows if r['hammer_price']):,}")

print("\ncoverage:")
for f in ("postcode", "property_key", "property_type", "auction_date", "bedrooms"):
    n = sum(1 for r in rows if r.get(f) not in (None, ""))
    print(f"  {f:14} {n:5}/{len(rows)}  ({100*n//len(rows)}%)")

# Re-offer signal: same property_key appearing across multiple events.
keys = collections.Counter(r["property_key"] for r in rows if r["property_key"])
repeat = {k: n for k, n in keys.items() if n > 1}
print(f"\nre-offers: {len(repeat)} properties appear in more than one auction")
print(f"  max appearances: {max(keys.values())}")
for k, n in sorted(repeat.items(), key=lambda x: -x[1])[:5]:
    ex = next(r for r in rows if r["property_key"] == k)
    print(f"  {n}x  {ex['address_raw'][:56]}")
