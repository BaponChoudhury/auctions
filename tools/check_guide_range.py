"""Is guide_price_max actually different from guide_price? Verify, don't assume."""
import json, pathlib, sys, collections
sys.path.insert(0, "../src")
from geo import load_cache

DATA = pathlib.Path("../data")
STAFFS = {"Stafford", "Stone", "Cannock Chase", "South Staffordshire",
          "Newcastle-under-Lyme", "Staffordshire Moorlands", "East Staffordshire",
          "Lichfield", "Tamworth", "Stoke-on-Trent"}

geo = load_cache()
lots = []
for p in ("sdl_all", "allsop_all"):
    lots += [json.loads(l) for l in (DATA / f"{p}.jsonl").open(encoding="utf-8")
             if l.strip()]
for l in lots:
    g = geo.get(l.get("postcode") or "") or {}
    l["district"] = g.get("admin_district")

rng = [l for l in lots if l.get("guide_price") and l.get("guide_price_max")]
print(f"lots with BOTH guide_price and guide_price_max: {len(rng):,}")
same = sum(1 for l in rng if l["guide_price"] == l["guide_price_max"])
print(f"  where the two are EQUAL: {same:,} ({100*same//max(len(rng),1)}%)")

print("\nby source:")
for src in sorted({l["source"] for l in rng}):
    sub = [l for l in rng if l["source"] == src]
    eq = sum(1 for l in sub if l["guide_price"] == l["guide_price_max"])
    print(f"  {src:10} {len(sub):5,} ranges, {eq:5,} equal")

print("\nsamples where they differ:")
for l in [x for x in rng if x["guide_price"] != x["guide_price_max"]][:6]:
    print(f"  {l['source']:9} £{l['guide_price']:>9,} - £{l['guide_price_max']:>9,}"
          f"   raw={l.get('result_raw','')[:44]}")

print("\nsamples where they are EQUAL (is this a parsing artefact?):")
for l in [x for x in rng if x["guide_price"] == x["guide_price_max"]][:6]:
    print(f"  {l['source']:9} £{l['guide_price']:>9,} = £{l['guide_price_max']:>9,}"
          f"   raw={l.get('result_raw','')[:44]}")

staffs_rng = [l for l in rng if l["district"] in STAFFS]
print(f"\nStaffordshire lots with a range: {len(staffs_rng)}")
diff = [l for l in staffs_rng if l["guide_price"] != l["guide_price_max"]]
print(f"  of those, genuinely different: {len(diff)}")
