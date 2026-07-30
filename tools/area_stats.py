"""What the area data unlocks: market breakdown by region and local authority."""
import collections, json, statistics, sys

sys.path.insert(0, "../src")
from geo import load_cache

geo = load_cache()
rows = []
for p in sys.argv[1:]:
    rows += [json.loads(l) for l in open(p, encoding="utf-8")]

matched = 0
for r in rows:
    g = geo.get(r.get("postcode") or "")
    r["region"] = g["region"] if g else None
    r["district"] = g["admin_district"] if g else None
    r["hpi_area"] = g["admin_district_code"] if g else None
    matched += bool(g)

print(f"lots: {len(rows)}   area resolved: {matched} ({100*matched//len(rows)}%)")
print(f"distinct local authorities: {len({r['district'] for r in rows if r['district']})}")
print(f"distinct HPI areas now available: "
      f"{len({r['hpi_area'] for r in rows if r['hpi_area']})}")

sold = [r for r in rows if r["hammer_price"]]


def table(key, title, min_n=25):
    grp = collections.defaultdict(list)
    for r in sold:
        if r[key]:
            grp[r[key]].append(r["hammer_price"])
    print(f"\n{title}")
    print(f"  {'':28} {'lots':>5} {'median':>10} {'total':>13}")
    for name, prices in sorted(grp.items(), key=lambda x: -len(x[1])):
        if len(prices) < min_n:
            continue
        print(f"  {name[:28]:28} {len(prices):5} "
              f"{'£'+format(int(statistics.median(prices)), ','):>10} "
              f"{'£'+format(sum(prices), ','):>13}")


table("region", "sold lots by region:", min_n=20)
table("district", "sold lots by local authority (top, n>=40):", min_n=40)

# The headline point: a national index cannot be right for this spread.
grp = collections.defaultdict(list)
for r in sold:
    if r["region"]:
        grp[r["region"]].append(r["hammer_price"])
meds = {k: statistics.median(v) for k, v in grp.items() if len(v) >= 20}
if meds:
    lo = min(meds, key=meds.get)
    hi = max(meds, key=meds.get)
    print(f"\nmedian sale spread: {lo} £{int(meds[lo]):,} -> {hi} £{int(meds[hi]):,} "
          f"({meds[hi]/meds[lo]:.1f}x)")
