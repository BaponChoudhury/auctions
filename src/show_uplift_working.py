"""Derivation of the guide -> hammer multiplier, with every step visible.

Shows the raw lots, each filter and what it changes, the sensitivity to how a
guide RANGE is read, and the selection bias that the headline number carries.
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

geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
for l in lots:
    g = geo.get(l.get("postcode") or "") or {}
    l["district"] = g.get("admin_district")


def med(rows, key=lambda l: l["hammer_price"] / l["guide_price"]):
    return np.median([key(l) for l in rows]) if rows else float("nan")


print("=" * 74)
print("  STEP 1 — who even publishes a guide price?")
print("=" * 74)
for src in sorted({l["source"] for l in lots}):
    sub = [l for l in lots if l["source"] == src]
    g = sum(1 for l in sub if l.get("guide_price"))
    print(f"    {src:11} {g:6,}/{len(sub):6,} lots have a guide  "
          f"({100*g//len(sub)}%)")
print("\n    Bond Wolfe and Clive Emson publish none, so the multiplier can only")
print("    ever be measured on SDL and Allsop stock.")

print("\n" + "=" * 74)
print("  STEP 2 — narrowing to lots where BOTH numbers exist")
print("=" * 74)
steps = [
    ("all lots", lots),
    ("has a guide price", [l for l in lots if l.get("guide_price")]),
    ("...and a hammer price", [l for l in lots if l.get("guide_price")
                               and l.get("hammer_price")]),
    ("...and status == sold", [l for l in lots if l.get("guide_price")
                               and l.get("hammer_price") and l["status"] == "sold"]),
    ("...and guide >= £5,000", [l for l in lots if l.get("guide_price")
                                and l.get("hammer_price") and l["status"] == "sold"
                                and l["guide_price"] >= 5000]),
]
prev = None
for label, rows in steps:
    usable = [l for l in rows if l.get("guide_price") and l.get("hammer_price")]
    m = med(usable) if usable else None
    extra = f"   median ratio {m:.3f}x" if m and not np.isnan(m) else ""
    delta = ""
    if prev is not None and m and not np.isnan(m):
        delta = f"  (moved {m-prev:+.3f})"
    print(f"    {label:26} {len(rows):6,} lots{extra}{delta}")
    if m and not np.isnan(m):
        prev = m
national = steps[-1][1]

print("\n    Why 'status == sold': sold_prior and sold_after lots rarely publish a")
print("    price, and where they do the sale was negotiated, not bid.")
print("    Why 'guide >= £5,000': a £1 guide gives a 9,900x ratio.")

print("\n" + "=" * 74)
print("  STEP 3 — Staffordshire only")
print("=" * 74)
staffs = [l for l in national if l["district"] in STAFFS]
r = np.array(sorted(l["hammer_price"] / l["guide_price"] for l in staffs))
print(f"    {len(r)} lots")
for q in (10, 25, 50, 75, 90):
    print(f"      p{q:<3} {np.percentile(r, q):.2f}x")
print(f"    mean {r.mean():.2f}x   <- pulled up by the tail; median is the honest one")

print("\n" + "=" * 74)
print("  STEP 4 — the biggest assumption: guide RANGES")
print("=" * 74)
rng = [l for l in staffs if l.get("guide_price_max")]
print(f"    {len(rng)}/{len(staffs)} Staffordshire lots publish a guide RANGE")
print("    (e.g. '£100,000 - £110,000'). We stored the LOWER bound as guide_price.")
if rng:
    lo_r = np.median([l["hammer_price"] / l["guide_price"] for l in rng])
    hi_r = np.median([l["hammer_price"] / l["guide_price_max"] for l in rng])
    print(f"      using the lower bound : {lo_r:.2f}x")
    print(f"      using the upper bound : {hi_r:.2f}x")
    print("    So for range-guided lots the multiplier depends on which end you read.")
flat = [l for l in staffs if not l.get("guide_price_max")]
if flat:
    print(f"    {len(flat)} lots have a single-figure guide; those give "
          f"{med(flat):.2f}x")

print("\n" + "=" * 74)
print("  STEP 5 — the selection bias you cannot remove")
print("=" * 74)
allg = [l for l in lots if l.get("guide_price") and l["guide_price"] >= 5000
        and l["district"] in STAFFS]
byst = collections.Counter(l["status"] for l in allg)
soldn = byst.get("sold", 0)
print(f"    Staffordshire lots with a guide: {len(allg)}")
for s, n in byst.most_common():
    print(f"      {s:12} {n:5}  ({100*n//len(allg)}%)")
print(f"\n    The 1.20x is measured ONLY on the {soldn} that sold under the hammer.")
print("    Lots that failed to reach reserve are invisible here, so the multiplier")
print("    answers 'if it sells, what does it fetch' - NOT 'what will this lot do'.")
print(f"    {byst.get('unsold',0)+byst.get('withdrawn',0)} of these did not sell at all.")

print("\n" + "=" * 74)
print("  THE NUMBER")
print("=" * 74)
print(f"    Staffordshire median: {np.percentile(r,50):.3f}x  -> quoted as 1.20x")
print(f"    on {len(r)} lots, from 2 of 4 auction houses, conditional on selling.")
print("    Treat 1.10x-1.49x as the working band, not 1.20x as a point estimate.")
print("=" * 74)
