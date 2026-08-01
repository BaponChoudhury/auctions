"""Stafford auction stock is not spread evenly — it clusters on a few streets.
Quantify that, because it changes where you'd actually look."""

import collections
import json
import pathlib
import re
import statistics
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache

DATA = pathlib.Path(__file__).parent.parent / "data"
STAFFS = ["Stafford", "Stone", "Cannock Chase", "South Staffordshire",
          "Newcastle-under-Lyme", "Staffordshire Moorlands",
          "East Staffordshire", "Lichfield", "Tamworth"]


def street_of(addr: str) -> str | None:
    """'67 Trenchard Avenue, Stafford, ST16 3RD' -> 'Trenchard Avenue'."""
    a = re.sub(r"^\s*[\d/&\-\sA-Za-z]*?(\d+[a-z]?)\s*[,\s]+", "", addr or "", count=1,
               flags=re.I)
    a = a.split(",")[0].strip()
    a = re.sub(r"\s+", " ", a)
    return a if 3 < len(a) < 40 and not a[0].isdigit() else None


geo = load_cache()
lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
for l in lots:
    g = geo.get(l.get("postcode") or "") or {}
    l["district"] = g.get("admin_district")
    l["street"] = street_of(l.get("address_raw", ""))

try:
    df = pd.read_csv(DATA / "features_partial.csv")
    df = df[df.hammer_price > 1000].copy()
    df["comp_n"] = pd.to_numeric(df.comp_median, errors="coerce")
    df["ratio"] = df.hammer_price / df.comp_n
    ratio_lookup = {(r.auction_date, int(r.hammer_price)): r.ratio
                    for _, r in df.iterrows()}
except FileNotFoundError:
    ratio_lookup = {}


def ratio_of(l):
    return ratio_lookup.get((l["auction_date"], l["hammer_price"]))


borough = [l for l in lots if l["district"] == "Stafford"]
print("=" * 70)
print("  STAFFORD — WHERE THE STOCK ACTUALLY IS")
print("=" * 70)

by_street = collections.defaultdict(list)
for l in borough:
    if l["street"]:
        by_street[l["street"]].append(l)

ranked = sorted(by_street.items(), key=lambda x: -len(x[1]))
top = [s for s in ranked if len(s[1]) >= 3]
covered = sum(len(v) for _, v in top)
print(f"\n  {len(borough)} lots sit on {len(by_street)} named streets.")
print(f"  {covered} of them ({100*covered//len(borough)}%) are on just "
      f"{len(top)} streets.\n")

print(f"  {'street':26} {'lots':>5} {'sold':>5} {'median':>10} {'vs local':>9}")
for s, v in top:
    pr = [x["hammer_price"] for x in v if x["hammer_price"]]
    rs = [r for r in (ratio_of(x) for x in v if x["hammer_price"]) if r and not pd.isna(r)]
    med = f"£{statistics.median(pr):,.0f}" if pr else "—"
    rr = f"{statistics.median(rs):.2f}x" if rs else "—"
    print(f"  {s[:26]:26} {len(v):5} {len(pr):5} {med:>10} {rr:>9}")

print("\n  Individual house numbers seen on the busiest street:")
if top:
    s0, v0 = top[0]
    nums = sorted({(l.get("property_key") or "|").split("|")[0] for l in v0} - {""},
                  key=lambda x: (len(x), x))
    print(f"    {s0}: {', '.join(nums)}")
    yrs = sorted({(l['auction_date'] or '')[:4] for l in v0 if l['auction_date']})
    print(f"    sold across {yrs[0]}-{yrs[-1]}, "
          f"{len({l['source'] for l in v0})} auction house(s)")

# Which type gives the best relative value across Staffordshire?
if len(df):
    ss = df[df.district.isin(STAFFS)]
    print("\n" + "-" * 70)
    print("BEST RELATIVE VALUE BY TYPE — wider Staffordshire")
    print("-" * 70)
    print(f"  {'type':12} {'sales':>6} {'median vs local':>16} {'median price':>13}")
    NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat",
            "O": "Land/comm"}
    rows = []
    for t, sub in ss.groupby("property_type"):
        r = sub.ratio.replace([np.inf, -np.inf], np.nan).dropna()
        if len(r) >= 15:
            rows.append((NAME.get(t, t), len(r), r.median(),
                         sub.hammer_price.median()))
    for name, n, med, price in sorted(rows, key=lambda x: x[2]):
        print(f"  {name:12} {n:6,} {med:15.2f}x   £{price:>10,.0f}")
    print("\n  Lower = cheaper relative to normal local sales.")
print("\n" + "=" * 70)
