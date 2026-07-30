"""What geography do we actually record, and what is only trapped in free text?"""
import collections, json, sys

rows = []
for p in sys.argv[1:]:
    rows += [json.loads(l) for l in open(p, encoding="utf-8")]

print(f"lots: {len(rows)}")
print("\nstructured geography fields present on a lot record:")
geo = [k for k in rows[0] if any(t in k for t in
       ("postcode", "address", "sector", "key", "town", "region", "area",
        "district", "county", "lat", "lng"))]
for k in geo:
    n = sum(1 for r in rows if r.get(k) not in (None, ""))
    print(f"  {k:16} {n:5}/{len(rows)}  ({100*n//len(rows)}%)")

missing = [k for k in ("town", "region", "county", "local_authority", "lat", "lng")
           if k not in rows[0]]
print(f"\nNOT stored as fields: {', '.join(missing)}")

# Outward code is the coarsest area we can derive today, with no extra lookup.
out = collections.Counter(r["postcode"].split()[0] for r in rows if r.get("postcode"))
print(f"\ndistinct outward codes: {len(out)}   sectors: "
      f"{len({r['postcode_sector'] for r in rows if r.get('postcode_sector')})}")
print("top 12 outward codes:")
for code, n in out.most_common(12):
    print(f"  {code:5} {n:4}")

print("\nwhat the address text carries beyond the postcode (samples):")
for r in rows[:6]:
    print(f"  {r['address_raw']}")
