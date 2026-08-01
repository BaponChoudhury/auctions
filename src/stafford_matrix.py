"""Price matrix for Stafford: every type x bedroom combination we can support.

Prints the range where there is enough local evidence and says plainly where
there is not, rather than filling the grid with numbers borrowed from Stoke.
"""

import collections
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache

DATA = pathlib.Path(__file__).parent.parent / "data"
NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat"}
MIN_LOCAL = 6          # below this, do not quote a range
# Stafford town and its ring. ST15 = Stone, ST18/19/20/21 = rural Stafford borough.
LOCAL = {"ST16", "ST17", "ST18", "ST19", "ST20", "ST21", "ST15"}


def outcode(pc):
    p = (pc or "").split()
    return p[0] if len(p) == 2 else ""


geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
for l in lots:
    g = geo.get(l.get("postcode") or "") or {}
    l["district"] = g.get("admin_district")
    l["outcode"] = outcode(l.get("postcode"))

local = [l for l in lots if l["outcode"] in LOCAL and l["hammer_price"]]
print("=" * 72)
print(f"  STAFFORD AREA PRICE MATRIX   ({len(local)} sold lots, "
      f"{'/'.join(sorted(LOCAL))})")
print("=" * 72)

print(f"\n  {'type':11} {'beds':>5} {'sales':>6} {'typical range':>25} "
      f"{'median':>10}")
print("  " + "-" * 68)

rows = collections.defaultdict(list)
for l in local:
    t = l.get("property_type")
    if t in NAME:
        rows[(t, l.get("bedrooms"))].append(l["hammer_price"])

quotable = []
for t in ("T", "S", "D", "F"):
    printed = False
    for beds in (1, 2, 3, 4):
        pr = rows.get((t, beds), [])
        if len(pr) >= MIN_LOCAL:
            a = np.array(sorted(pr))
            lo, hi = np.percentile(a, 25), np.percentile(a, 75)
            print(f"  {NAME[t]:11} {beds:>5} {len(a):6} "
                  f"{'£%s - £%s' % (f'{lo:,.0f}', f'{hi:,.0f}'):>25} "
                  f"£{np.percentile(a,50):>9,.0f}")
            quotable.append((NAME[t], beds, len(a), lo, hi))
            printed = True
        elif pr:
            print(f"  {NAME[t]:11} {beds:>5} {len(pr):6} "
                  f"{'too few to quote':>25}")
            printed = True
    # any-bed row for the type
    allpr = [p for (tt, _), v in rows.items() if tt == t for p in v]
    if len(allpr) >= MIN_LOCAL:
        a = np.array(sorted(allpr))
        print(f"  {NAME[t]:11} {'any':>5} {len(a):6} "
              f"{'£%s - £%s' % (f'{np.percentile(a,25):,.0f}', f'{np.percentile(a,75):,.0f}'):>25} "
              f"£{np.percentile(a,50):>9,.0f}")
    elif not printed:
        print(f"  {NAME[t]:11} {'any':>5} {len(allpr):6} {'no local sales':>25}")
    print()

print("  " + "-" * 68)
print("  Rows marked 'too few to quote' have local sales but not enough to")
print("  give an honest range. Nothing here is borrowed from outside the area.")

# Bedroom data coverage caveat.
have_beds = sum(1 for l in local if l.get("bedrooms"))
print(f"\n  Note: only {have_beds}/{len(local)} local sold lots record a bedroom")
print(f"  count ({100*have_beds//len(local)}%), so the 'any' rows rest on more")
print("  evidence than the per-bedroom rows.")
print("=" * 72)
