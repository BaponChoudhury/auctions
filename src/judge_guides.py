"""Judge live guide prices against the Stafford matrix.

Chain: guide -> expected hammer (x1.20 locally) -> compare to what that type and
bed count actually fetches around Stafford.

Conditional formats (Modern Method of Auction, Secure Sale) are flagged, not
scored: their "guide" is a starting bid, the buyer pays a reservation fee of
roughly 4-5% on top, and the local x1.20 uplift was measured on unconditional
auctions only.
"""

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache

DATA = pathlib.Path(__file__).parent.parent / "data"
LOCAL_OUT = {"ST15", "ST16", "ST17", "ST18", "ST19", "ST20", "ST21"}
NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat"}
UPLIFT_MID, UPLIFT_LO, UPLIFT_HI = 1.20, 1.10, 1.49

# The live Rightmove auction lots for Stafford, read on 2026-08-01.
LIVE = [
    # address, type, beds, guide, seller, unconditional?
    ("12 Byron Close, ST16 3NY",        "S", 3,  34_000, "Under The Hammer", True),
    ("2 Beeston Ridge, ST17 9LA",       "D", 3, 108_000, "Auction House", True),
    ("Sandon Road, ST16 3ES (block of 3)", "T", 8, 240_000, "Butters John Bee", True),
    ("Albert Terrace, ST16 3EX (tenanted)", "T", 3, 100_000, "Pattinson (Secure Sale)", False),
    ("John Amery Drive, ST17 9PE",      "T", 2, 135_000, "Pattinson (Secure Sale)", False),
    ("Prospect Road, Beaconside, ST16", "T", 3, 130_000, "D B Roberts (MMoA)", False),
    ("Bellasis Street, ST16",           "T", 2, 110_000, "D B Roberts (MMoA)", False),
    ("Washington Drive, Stafford",      "S", 3, 180_000, "Connells", False),
    ("Weston Road, ST16 (tenanted)",    "S", 4, 160_000, "Bridgfords", False),
]


def outcode(pc):
    p = (pc or "").split()
    return p[0] if len(p) == 2 else ""


geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
local = [l for l in lots if outcode(l.get("postcode")) in LOCAL_OUT and l["hammer_price"]]


def matrix(ptype, beds):
    exact = [l["hammer_price"] for l in local
             if l.get("property_type") == ptype and l.get("bedrooms") == beds]
    anyb = [l["hammer_price"] for l in local if l.get("property_type") == ptype]
    if len(exact) >= 6:
        return np.array(sorted(exact)), f"{beds}-bed", len(exact)
    if len(anyb) >= 6:
        return np.array(sorted(anyb)), "any beds", len(anyb)
    return None, None, len(anyb)


print("=" * 78)
print("  LIVE STAFFORD AUCTION LOTS — GUIDE JUDGED AGAINST THE MATRIX")
print("=" * 78)
print(f"  Local uplift: hammer = guide x {UPLIFT_MID:.2f} "
      f"(usual band {UPLIFT_LO:.2f}-{UPLIFT_HI:.2f}); only 5% sell at or below guide.\n")

for addr, t, beds, guide, seller, uncond in LIVE:
    exp = guide * UPLIFT_MID
    band, basis, n = matrix(t, beds)
    print("-" * 78)
    print(f"  {addr}")
    print(f"    {NAME.get(t,t)}, {beds} bed   guide £{guide:,}   {seller}")
    if not uncond:
        print("    ** conditional format — reservation fee ~4-5% on top, and the")
        print("       x1.20 uplift does NOT apply. Guide read as a starting bid. **")
    if band is None:
        print(f"    no local benchmark for this type ({n} sales) — cannot judge")
        continue
    p25, p50, p75 = (np.percentile(band, 25), np.percentile(band, 50),
                     np.percentile(band, 75))
    print(f"    matrix ({basis}, {n} local sales): "
          f"£{p25:,.0f} - £{p75:,.0f}, median £{p50:,.0f}")
    if uncond:
        print(f"    expected hammer from guide: £{exp:,.0f} "
              f"(band £{guide*UPLIFT_LO:,.0f} - £{guide*UPLIFT_HI:,.0f})")
        if exp < p25:
            verdict = "CHEAP vs local sales — check the legal pack for why"
        elif exp > p75:
            verdict = "EXPENSIVE — expected hammer sits above the local band"
        else:
            verdict = "FAIR — expected hammer lands inside the local band"
        print(f"    -> {verdict}")
        print(f"    -> walk-away: £{p75:,.0f}")
    else:
        pos = ("below" if guide < p25 else "above" if guide > p75 else "inside")
        print(f"    starting bid sits {pos} the local hammer band")
        print(f"    -> add ~4-5% reservation fee before comparing")

print("=" * 78)
