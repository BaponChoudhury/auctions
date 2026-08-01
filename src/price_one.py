"""Price a single live lot: what has this postcode sector actually paid?

  python price_one.py --postcode "ST20 0BU" --type D --guide 230000
"""

import argparse
import bisect
import collections
import csv
import json
import pathlib
import statistics
import sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache
from ppd_match import C_DATE, C_PAON, C_POSTCODE, C_PRICE, C_TYPE, PPD_DIR

DATA = pathlib.Path(__file__).parent.parent / "data"
NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat", "O": "Land/comm"}
STAFFS = {"Stafford", "Stone", "Cannock Chase", "South Staffordshire",
          "Newcastle-under-Lyme", "Staffordshire Moorlands", "East Staffordshire",
          "Lichfield", "Tamworth"}


def sector_of(pc):
    p = (pc or "").split()
    return f"{p[0]} {p[1][0]}" if len(p) == 2 and p[1] else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--postcode", required=True)
    ap.add_argument("--type", required=True)
    ap.add_argument("--guide", type=int)
    ap.add_argument("--months", type=int, default=36)
    args = ap.parse_args()

    sec = sector_of(args.postcode)
    out = args.postcode.split()[0]
    print("=" * 68)
    print(f"  {NAME.get(args.type, args.type)} — {args.postcode}  (sector {sec})")
    if args.guide:
        print(f"  Guide: £{args.guide:,}")
    print("=" * 68)

    # --- Land Registry: what NORMAL sales in this sector fetch -------------
    hi = date.today()
    lo = (hi - timedelta(days=30 * args.months)).isoformat()
    same, sector_all = [], []
    for path in sorted(PPD_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) <= C_PAON:
                    continue
                if sector_of(row[C_POSTCODE].strip().upper()) != sec:
                    continue
                if not (lo <= row[C_DATE][:10] <= hi.isoformat()):
                    continue
                try:
                    p = int(row[C_PRICE])
                except ValueError:
                    continue
                sector_all.append(p)
                if row[C_TYPE] == args.type:
                    same.append(p)

    print(f"\n  LAND REGISTRY — normal open-market sales in {sec}, "
          f"last {args.months} months")
    for label, arr in ((f"{NAME.get(args.type, args.type)} only", same),
                       ("all types", sector_all)):
        if len(arr) >= 5:
            a = np.array(sorted(arr))
            print(f"    {label:22} {len(a):4} sales   "
                  f"median £{np.percentile(a,50):>9,.0f}   "
                  f"p25-p75 £{np.percentile(a,25):,.0f}-£{np.percentile(a,75):,.0f}")
        else:
            print(f"    {label:22} {len(arr):4} sales   too few to use")

    # --- auction discount for this type across Staffordshire --------------
    geo = load_cache()
    lots = []
    for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
        f = DATA / f"{p}.jsonl"
        if f.exists():
            lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
    for l in lots:
        g = geo.get(l.get("postcode") or "") or {}
        l["district"] = g.get("admin_district")

    try:
        import pandas as pd
        df = pd.read_csv(DATA / "features.csv")
        df = df[(df.hammer_price > 1000) & df.district.isin(STAFFS)].copy()
        df["comp_n"] = pd.to_numeric(df.comp_median, errors="coerce")
        df["ratio"] = df.hammer_price / df.comp_n
        r = df[df.property_type == args.type].ratio.replace(
            [np.inf, -np.inf], np.nan).dropna()
    except Exception:
        r = None

    print(f"\n  AUCTION DISCOUNT — {NAME.get(args.type, args.type)} across Staffordshire")
    if r is not None and len(r) >= 10:
        print(f"    {len(r)} auction sales")
        print(f"    typical  {np.percentile(r,50):.2f}x of normal local value")
        print(f"    range    {np.percentile(r,25):.2f}x - {np.percentile(r,75):.2f}x")
    else:
        print(f"    only {0 if r is None else len(r)} sales — not enough for this type")

    # --- what auction actually paid for this type nearby ------------------
    near = [l for l in lots if l["hammer_price"]
            and l.get("property_type") == args.type
            and (l.get("postcode") or "").split()[:1] == [out]]
    wider = [l for l in lots if l["hammer_price"]
             and l.get("property_type") == args.type and l["district"] in STAFFS]
    print(f"\n  AUCTION SALES, same type")
    print(f"    in {out}: {len(near)}")
    for l in sorted(near, key=lambda x: x["auction_date"] or "", reverse=True)[:5]:
        print(f"      {l['auction_date']}  £{l['hammer_price']:>9,}  "
              f"{l['address_raw'][:44]}")
    if len(wider) >= 5:
        a = np.array(sorted(x["hammer_price"] for x in wider))
        print(f"    across Staffordshire: {len(a)} sales, "
              f"median £{np.percentile(a,50):,.0f}, "
              f"p25-p75 £{np.percentile(a,25):,.0f}-£{np.percentile(a,75):,.0f}")

    # --- bring it together -------------------------------------------------
    print("\n" + "-" * 68)
    print("  WHAT TO BID")
    print("-" * 68)
    base = np.percentile(np.array(same), 50) if len(same) >= 5 else (
        np.percentile(np.array(sector_all), 50) if len(sector_all) >= 5 else None)
    if base and r is not None and len(r) >= 10:
        lo_r, mid_r, hi_r = (np.percentile(r, 25), np.percentile(r, 50),
                             np.percentile(r, 75))
        print(f"    normal value here      £{base:,.0f}")
        print(f"    auction discount       {lo_r:.2f}x - {hi_r:.2f}x")
        print(f"    -> open around         £{base*lo_r:,.0f}")
        print(f"    -> fair                £{base*mid_r:,.0f}")
        print(f"    -> stop by             £{base*hi_r:,.0f}")
        if args.guide:
            print(f"\n    guide £{args.guide:,} is {args.guide/base:.2f}x normal value")
            verdict = ("already at the top of the auction range - little room"
                       if args.guide / base >= hi_r else
                       "in the normal auction range" if args.guide / base >= lo_r else
                       "below the usual auction range - worth a look")
            print(f"    that is {verdict}")
    else:
        print("    Not enough local evidence to give a range for this type here.")
    print("\n    Hammer only. Add buyer's fees and any works on top.")
    print("=" * 68)


if __name__ == "__main__":
    main()
