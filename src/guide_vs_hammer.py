"""What does a guide price actually convert to?

The matrix is built from HAMMER prices. A guide is a different thing - in
unconditional auctions it is usually set below expected value to draw bidders.
To judge a live lot's guide you need the local guide -> hammer relationship,
not the national one.

Only SDL and Allsop publish guides, so this is measured on their lots.
"""

import collections
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache

DATA = pathlib.Path(__file__).parent.parent / "data"
STAFFS = {"Stafford", "Stone", "Cannock Chase", "South Staffordshire",
          "Newcastle-under-Lyme", "Staffordshire Moorlands", "East Staffordshire",
          "Lichfield", "Tamworth", "Stoke-on-Trent"}
NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat", "O": "Land/comm"}

geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
for l in lots:
    g = geo.get(l.get("postcode") or "") or {}
    l["district"] = g.get("admin_district")

pairs = [l for l in lots
         if l.get("guide_price") and l.get("hammer_price")
         and l["guide_price"] >= 5000 and l["status"] == "sold"]
staffs = [l for l in pairs if l["district"] in STAFFS]

print("=" * 66)
print("  GUIDE PRICE -> HAMMER PRICE")
print("=" * 66)


def show(label, rows):
    if len(rows) < 10:
        print(f"\n  {label}: only {len(rows)} lots - too few")
        return None
    r = np.array(sorted(l["hammer_price"] / l["guide_price"] for l in rows))
    print(f"\n  {label}  ({len(r)} sold lots with both figures)")
    print(f"    typical hammer = {np.percentile(r,50):.2f}x guide "
          f"(+{100*(np.percentile(r,50)-1):.0f}%)")
    print(f"    p25-p75        {np.percentile(r,25):.2f}x - {np.percentile(r,75):.2f}x")
    print(f"    p10-p90        {np.percentile(r,10):.2f}x - {np.percentile(r,90):.2f}x")
    print(f"    sold AT or BELOW guide: {100*(r<=1.0).mean():.0f}% of the time")
    return r


nat = show("Everywhere", pairs)
loc = show("Staffordshire", staffs)

if loc is not None:
    print("\n  by property type, Staffordshire:")
    print(f"    {'type':11} {'n':>4} {'typical':>9} {'p25-p75':>17}")
    by_t = collections.defaultdict(list)
    for l in staffs:
        by_t[l.get("property_type")].append(l["hammer_price"] / l["guide_price"])
    for t, v in sorted(by_t.items(), key=lambda x: -len(x[1])):
        if len(v) < 8:
            continue
        a = np.array(sorted(v))
        print(f"    {NAME.get(t, '?'):11} {len(a):4} {np.percentile(a,50):8.2f}x "
              f"{f'{np.percentile(a,25):.2f}x - {np.percentile(a,75):.2f}x':>17}")

print("\n" + "-" * 66)
print("  HOW TO READ A LIVE GUIDE")
print("-" * 66)
if loc is not None:
    lo, mid, hi = (np.percentile(loc, 25), np.percentile(loc, 50),
                   np.percentile(loc, 75))
    print(f"    expected hammer  =  guide x {mid:.2f}   (likely {lo:.2f}-{hi:.2f}x)")
    print(f"    so a £100,000 guide typically fetches "
          f"£{100000*mid:,.0f}, usually £{100000*lo:,.0f}-£{100000*hi:,.0f}")
print("\n  Compare THAT figure against the matrix, not the guide itself.")
print("=" * 66)
