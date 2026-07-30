"""Field-coverage and vocabulary check for any scraper's output."""
import collections, json, sys

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
print(f"lots: {len(rows)}   source: {rows[0]['source']}")
print("status:", dict(collections.Counter(r["status"] for r in rows).most_common()))
print("types :", dict(collections.Counter(r["property_type"] for r in rows).most_common()))
print("\ncoverage:")
for f in ("postcode", "postcode_sector", "property_key", "property_type", "bedrooms",
          "auction_date", "guide_price", "hammer_price", "description", "lot_url"):
    n = sum(1 for r in rows if r.get(f) not in (None, "", 0))
    print(f"  {f:16} {n:4}/{len(rows)}  ({100*n//len(rows)}%)")
print("\nsample sold:")
for r in [r for r in rows if r["hammer_price"]][:5]:
    print(f"  £{r['hammer_price']:>9,}  {r['property_type'] or '-'}  {r['bedrooms'] or '-'}bed  "
          f"{r['address_raw'][:44]:44} key={r['property_key']}")
print("\nsample non-sold:")
seen = set()
for r in rows:
    if r["status"] not in seen and not r["hammer_price"]:
        seen.add(r["status"])
        print(f"  {r['status']:11} raw={r['result_raw'][:66]!r}")
