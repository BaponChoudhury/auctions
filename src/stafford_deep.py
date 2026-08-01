"""Deep dive on Stafford.

The borough alone has 95 lots, which is too thin to lean on. This widens the
view three ways and keeps them clearly separate:
  1. Stafford borough itself (what actually sold, every lot)
  2. ST postcode district (how the town's postcodes behave)
  3. Wider Staffordshire (a robust discount benchmark from a real sample)

Also answers the practical question: whose catalogue do I actually need to watch
to see Stafford stock?
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
STAFFS = ["Stafford", "Stone", "Cannock Chase", "South Staffordshire",
          "Newcastle-under-Lyme", "Staffordshire Moorlands",
          "East Staffordshire", "Lichfield", "Tamworth", "Stoke-on-Trent"]
TYPE_NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat",
             "O": "Land/comm"}
HOUSE = {"sdl": "SDL", "bondwolfe": "Bond Wolfe", "allsop": "Allsop",
         "emson": "Clive Emson"}


def money(n):
    return f"£{n:,.0f}" if n else "—"


geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
for l in lots:
    g = geo.get(l.get("postcode") or "") or {}
    l["district"] = g.get("admin_district")

borough = [l for l in lots if l["district"] == "Stafford"]
st_town = [l for l in lots
           if ((l.get("postcode") or "").split() or [""])[0][:4] in
           ("ST16", "ST17", "ST18", "ST19", "ST20", "ST21")]
county = [l for l in lots if l["district"] in STAFFS]

print("=" * 70)
print("  STAFFORD — DEEP DIVE")
print("=" * 70)
print(f"\n  Stafford borough      {len(borough):5,} lots  "
      f"{sum(1 for l in borough if l['hammer_price']):4} with a price")
print(f"  ST16-ST21 postcodes   {len(st_town):5,} lots  "
      f"{sum(1 for l in st_town if l['hammer_price']):4} with a price")
print(f"  Wider Staffordshire   {len(county):5,} lots  "
      f"{sum(1 for l in county if l['hammer_price']):4} with a price")

# ---- whose catalogue do I watch? ---------------------------------------
print("\n" + "-" * 70)
print("WHOSE CATALOGUE CARRIES STAFFORD STOCK")
print("-" * 70)
src = collections.Counter(l["source"] for l in borough)
for s, n in src.most_common():
    sold = sum(1 for l in borough if l["source"] == s and l["hammer_price"])
    yrs = sorted({(l["auction_date"] or "")[:4] for l in borough
                  if l["source"] == s and l["auction_date"]})
    print(f"  {HOUSE.get(s, s):13} {n:4} lots ({sold:3} priced)   "
          f"{yrs[0] if yrs else '?'}-{yrs[-1] if yrs else '?'}")
print("\n  -> that is the catalogue to watch for Stafford.")

# ---- every sold lot ----------------------------------------------------
df = None
try:
    df = pd.read_csv(DATA / "features_partial.csv")
    df = df[df.hammer_price > 1000].copy()
    df["comp_n"] = pd.to_numeric(df.comp_median, errors="coerce")
    df["ratio"] = df.hammer_price / df.comp_n
except FileNotFoundError:
    pass

sold = sorted([l for l in borough if l["hammer_price"]],
              key=lambda l: l["auction_date"] or "")
ratio_by_key = {}
if df is not None:
    sb = df[df.district == "Stafford"]
    for _, r in sb.iterrows():
        ratio_by_key[(r.auction_date, int(r.hammer_price))] = r.ratio

print("\n" + "-" * 70)
print(f"EVERY STAFFORD LOT THAT SOLD WITH A PRICE  ({len(sold)})")
print("-" * 70)
print(f"  {'date':11} {'type':10} {'price':>9} {'vs local':>9}  address")
for l in sold:
    key = (l["auction_date"], l["hammer_price"])
    r = ratio_by_key.get(key)
    rs = f"{r:.2f}x" if r and not pd.isna(r) else "—"
    print(f"  {str(l['auction_date']):11} "
          f"{TYPE_NAME.get(l.get('property_type'), '?'):10} "
          f"{money(l['hammer_price']):>9} {rs:>9}  {l['address_raw'][:40]}")

# ---- sector detail -----------------------------------------------------
print("\n" + "-" * 70)
print("BY POSTCODE SECTOR (Stafford borough)")
print("-" * 70)
sect = collections.defaultdict(list)
for l in borough:
    if l["postcode_sector"]:
        sect[l["postcode_sector"]].append(l)
print(f"  {'sector':10} {'lots':>5} {'sold':>5} {'median':>10}")
for s, v in sorted(sect.items(), key=lambda x: -len(x[1])):
    pr = [x["hammer_price"] for x in v if x["hammer_price"]]
    med = money(statistics.median(pr)) if pr else "—"
    print(f"  {s:10} {len(v):5} {len(pr):5} {med:>10}")

# ---- robust discount from the wider county -----------------------------
if df is not None:
    print("\n" + "-" * 70)
    print("DISCOUNT BENCHMARK — borough vs wider Staffordshire")
    print("-" * 70)
    print(f"  {'area':26} {'sales':>6} {'median':>9} {'p25':>7} {'p75':>7}")
    for label, sub in (("Stafford borough", df[df.district == "Stafford"]),
                       ("Wider Staffordshire", df[df.district.isin(STAFFS)])):
        r = sub.ratio.replace([np.inf, -np.inf], np.nan).dropna()
        if len(r) >= 8:
            print(f"  {label:26} {len(r):6,} {r.median():8.2f}x "
                  f"{r.quantile(.25):6.2f}x {r.quantile(.75):6.2f}x")
    print("\n  The wider figure is the one to trust; the borough sample is small.")

    print("\n  by property type, wider Staffordshire:")
    ss = df[df.district.isin(STAFFS)]
    print(f"    {'type':10} {'sales':>6} {'median vs local':>16}")
    for t, sub in ss.groupby("property_type"):
        r = sub.ratio.replace([np.inf, -np.inf], np.nan).dropna()
        if len(r) >= 15:
            print(f"    {TYPE_NAME.get(t, t):10} {len(r):6,} {r.median():15.2f}x")

# ---- repeats -----------------------------------------------------------
print("\n" + "-" * 70)
print("PROPERTIES OFFERED MORE THAN ONCE (Stafford borough)")
print("-" * 70)
keys = collections.Counter(l["property_key"] for l in borough if l["property_key"])
for k, n in sorted(((k, n) for k, n in keys.items() if n > 1), key=lambda x: -x[1]):
    hist = sorted([l for l in borough if l["property_key"] == k],
                  key=lambda l: l["auction_date"] or "")
    print(f"\n  {n}x  {hist[0]['address_raw'][:52]}")
    for h in hist:
        print(f"        {h['auction_date']}  {h['status']:11} "
              f"{money(h['hammer_price']):>9}  {HOUSE.get(h['source'], h['source'])}")
print("\n" + "=" * 70)
