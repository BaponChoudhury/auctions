"""Every ST16-area lot we hold, what it did, and what a bid range looks like.

Two separate things, kept apart on purpose:
  1. SOLD history -> what this area actually pays (the basis for a bid range)
  2. Anything still LIVE (unsold / re-entered / no result yet) -> actually biddable

The corpus is past results. For a lot going under the hammer next week you need
the current catalogue; this prices the AREA, not a specific live lot.
"""

import collections
import json
import pathlib
import statistics
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache

DATA = pathlib.Path(__file__).parent.parent / "data"
NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat", "O": "Land/comm"}
HOUSE = {"sdl": "SDL", "bondwolfe": "Bond Wolfe", "allsop": "Allsop",
         "emson": "Clive Emson"}
LIVE = ("unsold", "listed", "postponed")


def outcode(pc):
    return (pc or "").split()[0] if pc and " " in pc else ""


geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]

# ST16 plus its immediate neighbours - one outcode alone is too thin.
NEAR = ("ST16", "ST17", "ST18")
area = [l for l in lots if outcode(l.get("postcode")) in NEAR]
st16 = [l for l in area if outcode(l.get("postcode")) == "ST16"]

try:
    df = pd.read_csv(DATA / "features_partial.csv")
    df = df[df.hammer_price > 1000].copy()
    df["comp_n"] = pd.to_numeric(df.comp_median, errors="coerce")
    df["ratio"] = df.hammer_price / df.comp_n
    RAT = {(r.auction_date, int(r.hammer_price)): r.ratio for _, r in df.iterrows()}
except FileNotFoundError:
    RAT = {}


def ratio(l):
    r = RAT.get((l["auction_date"], l["hammer_price"]))
    return None if r is None or pd.isna(r) else r


print("=" * 74)
print("  ST16 AND NEIGHBOURS (ST16 / ST17 / ST18)")
print("=" * 74)
print(f"  ST16 only        {len(st16):4} lots, "
      f"{sum(1 for l in st16 if l['hammer_price']):3} with a price")
print(f"  ST16+17+18       {len(area):4} lots, "
      f"{sum(1 for l in area if l['hammer_price']):3} with a price")

# ---------------------------------------------------------------- live ---
live = [l for l in area if l["status"] in LIVE]
live.sort(key=lambda l: l["auction_date"] or "", reverse=True)
print("\n" + "-" * 74)
print("STILL LIVE / DID NOT SELL — these are the ones you could chase")
print("-" * 74)
if not live:
    print("  none in the corpus")
for l in live[:15]:
    g = l.get("guide_price")
    guide = f"£{g:,}" if g else "—"
    print(f"  {str(l['auction_date']):11} {l['status']:10} "
          f"{NAME.get(l.get('property_type'), '?'):10} guide {guide:>9}  "
          f"{l['address_raw'][:38]}")
    print(f"              {HOUSE.get(l['source'], l['source'])}  {l['lot_url'][:66]}")

# --------------------------------------------------------- sold history ---
sold = [l for l in area if l["hammer_price"] and l.get("property_type") in NAME]
print("\n" + "-" * 74)
print("WHAT THIS AREA ACTUALLY PAYS  (sold lots, ST16/17/18)")
print("-" * 74)
print(f"  {'type':11} {'n':>4} {'p10':>9} {'p25':>9} {'median':>9} "
      f"{'p75':>9} {'p90':>9}")
by_t = collections.defaultdict(list)
for l in sold:
    by_t[l["property_type"]].append(l["hammer_price"])
for t, pr in sorted(by_t.items(), key=lambda x: -len(x[1])):
    if len(pr) < 4:
        continue
    a = np.array(sorted(pr))
    print(f"  {NAME[t]:11} {len(a):4} "
          + " ".join(f"£{np.percentile(a, q):>8,.0f}" for q in (10, 25, 50, 75, 90)))

# ------------------------------------------------------------ bid range ---
print("\n" + "-" * 74)
print("BID RANGE GUIDE")
print("-" * 74)
print("  Two ways to frame a bid. Use both and take the overlap.\n")

print("  A) From what similar lots fetched here")
for t, pr in sorted(by_t.items(), key=lambda x: -len(x[1])):
    if len(pr) < 6:
        continue
    a = np.array(sorted(pr))
    print(f"     {NAME[t]:11} typical {np.percentile(a,25):>8,.0f} - "
          f"{np.percentile(a,75):>8,.0f}   (walk away above "
          f"£{np.percentile(a,90):,.0f})")

print("\n  B) As a fraction of normal open-market value for the same street")
rs = collections.defaultdict(list)
for l in sold:
    r = ratio(l)
    if r:
        rs[l["property_type"]].append(r)
for t, v in sorted(rs.items(), key=lambda x: -len(x[1])):
    if len(v) < 6:
        continue
    a = np.array(sorted(v))
    print(f"     {NAME[t]:11} bid {np.percentile(a,25):.2f}x - "
          f"{np.percentile(a,50):.2f}x of local value; "
          f"above {np.percentile(a,75):.2f}x you are paying up")

print("\n  Worked example — a mid-terrace on a normal ST16 street:")
tr = sorted(by_t.get("T", []))
trr = sorted(rs.get("T", []))
if len(tr) >= 6 and len(trr) >= 6:
    print(f"     comparable sales say      £{np.percentile(tr,25):,.0f} - "
          f"£{np.percentile(tr,75):,.0f}")
    print(f"     if Rightmove says the doer-upper next door is worth £140,000,")
    print(f"     then {np.percentile(trr,25):.2f}x-{np.percentile(trr,50):.2f}x gives "
          f"£{140000*np.percentile(trr,25):,.0f} - £{140000*np.percentile(trr,50):,.0f}")
    print(f"     -> open around £{140000*np.percentile(trr,25):,.0f}, "
          f"stop by £{140000*np.percentile(trr,75):,.0f}")

print("\n  Add refurb cost and fees on top — these are hammer prices only,")
print("  and buyer's fees are charged separately.")
print("\n" + "=" * 74)
