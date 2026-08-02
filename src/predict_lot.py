"""Predict what ONE lot will sell for.

Everything else in this project analyses the corpus. This applies it: give it a
postcode, a property type and (optionally) a guide price, and it returns an
expected hammer price with an honest interval.

Three independent estimates are shown, because agreeing estimates are worth more
than one confident number:

  1. MODEL      gradient boosting on area + type + Land Registry comps
  2. GUIDE      guide x the locally measured guide-to-hammer uplift
  3. COMPARABLE what this type actually fetched at auction near this postcode

The interval is not invented: it comes from the model's own out-of-sample error
distribution, measured on later auctions it never trained on.

  python predict_lot.py --postcode "ST16 3RD" --type S --beds 3 --guide 95000
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
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache
from ppd_match import C_DATE, C_PAON, C_POSTCODE, C_PRICE, C_TYPE, PPD_DIR

DATA = pathlib.Path(__file__).parent.parent / "data"
NAME = {"D": "Detached", "S": "Semi-detached", "T": "Terraced", "F": "Flat",
        "O": "Land/commercial"}
FEATURES = ["comp_median", "comp_count", "comp_iqr", "bedrooms"]
CATS = ["property_type", "region", "district"]


def sector_of(pc):
    p = (pc or "").split()
    return f"{p[0]} {p[1][0]}" if len(p) == 2 and p[1] else None


def ppd_sector_index(sectors):
    idx = collections.defaultdict(list)
    for path in sorted(PPD_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) <= C_PAON:
                    continue
                s = sector_of(row[C_POSTCODE].strip().upper())
                if s not in sectors:
                    continue
                try:
                    idx[(s, row[C_TYPE])].append((row[C_DATE][:10], int(row[C_PRICE])))
                except ValueError:
                    continue
    for k in idx:
        idx[k].sort()
    return idx


def comps(idx, sector, ptype, as_at, months=24):
    """Median / count / IQR of nearby sales in the window before `as_at`."""
    if not sector:
        return None, 0, None
    hi = date.fromisoformat(as_at)
    lo = (hi - timedelta(days=30 * months)).isoformat()
    keys = [(sector, ptype)] if ptype else [(sector, t) for t in "DSTFO"]
    prices = []
    for k in keys:
        rows = idx.get(k)
        if not rows:
            continue
        i = bisect.bisect_left(rows, (lo, 0))
        j = bisect.bisect_left(rows, (hi.isoformat(), 0))
        prices += [p for _, p in rows[i:j]]
    if not prices:
        return None, 0, None
    prices.sort()
    iqr = (prices[int(len(prices) * .75)] - prices[int(len(prices) * .25)]
           if len(prices) >= 4 else None)
    return int(statistics.median(prices)), len(prices), iqr


def build_model(df):
    """Train on everything before the last 20% of auctions; measure error on the rest."""
    df = df.sort_values("auction_date")
    cut = int(len(df) * 0.8)
    tr, te = df.iloc[:cut], df.iloc[cut:]

    def prep(d):
        X = d[FEATURES].apply(pd.to_numeric, errors="coerce").copy()
        for c in CATS:
            X[c] = d[c].astype("category")
        return X

    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, max_depth=6,
                                      random_state=0,
                                      categorical_features="from_dtype")
    m.fit(prep(tr), np.log(tr.hammer_price.values))
    pred = np.exp(m.predict(prep(te)))
    err = pred / te.hammer_price.values           # ratio, not absolute
    # Median ABSOLUTE percentage error. The median of the raw ratio is ~1.0 and
    # reporting that as "error" makes a 17%-error model look perfect.
    mdape = float(np.median(np.abs(pred - te.hammer_price.values)
                            / te.hammer_price.values) * 100)
    return m, np.array(sorted(err)), len(tr), len(te), mdape


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--postcode", required=True)
    ap.add_argument("--type", required=True, help="D/S/T/F/O")
    ap.add_argument("--beds", type=int)
    ap.add_argument("--guide", type=int)
    ap.add_argument("--features", default=str(DATA / "features.csv"))
    args = ap.parse_args()

    pc = args.postcode.upper().strip()
    sector = sector_of(pc)
    if not sector:
        sys.exit(f"'{args.postcode}' does not look like a full postcode "
                 f"(need e.g. 'ST16 3RD')")

    geo = load_cache().get(pc) or {}
    region = geo.get("region") or ""
    district = geo.get("admin_district") or ""

    df = pd.read_csv(args.features)
    df = df[(df.hammer_price > 1000) & df.property_type.isin(["D", "S", "T", "F"])]
    model, err, n_tr, n_te, mdape = build_model(df)

    idx = ppd_sector_index({sector})
    med, cnt, iqr = comps(idx, sector, args.type, date.today().isoformat())

    print("=" * 70)
    print(f"  {NAME.get(args.type, args.type)}"
          + (f", {args.beds} bed" if args.beds else "")
          + f" — {pc}")
    if district:
        print(f"  {district}, {region}   (sector {sector})")
    print("=" * 70)

    if med is None:
        print("\n  No Land Registry sales of this type in this sector — the model")
        print("  has nothing to anchor on. Widen the type or check the postcode.")
        return
    print(f"\n  Land Registry, {sector}, last 24 months:")
    print(f"    {cnt} sales of this type, median £{med:,}")

    # ---- 1. model ----------------------------------------------------------
    row = pd.DataFrame([{"comp_median": med, "comp_count": cnt,
                         "comp_iqr": iqr if iqr else np.nan,
                         "bedrooms": args.beds if args.beds else np.nan,
                         "property_type": args.type, "region": region,
                         "district": district}])
    for c in CATS:
        row[c] = row[c].astype("category")
    point = float(np.exp(model.predict(row[FEATURES + CATS])[0]))
    lo80, hi80 = point / np.percentile(err, 90), point / np.percentile(err, 10)
    lo50, hi50 = point / np.percentile(err, 75), point / np.percentile(err, 25)

    print("\n" + "-" * 70)
    print("  1. MODEL")
    print("-" * 70)
    print(f"    best estimate      £{point:,.0f}")
    print(f"    50% confidence     £{lo50:,.0f} - £{hi50:,.0f}")
    print(f"    80% confidence     £{lo80:,.0f} - £{hi80:,.0f}")
    print(f"    (interval from {n_te:,} later auctions the model never saw;")
    print(f"     median absolute error {mdape:.0f}%)")

    # ---- 2. guide ----------------------------------------------------------
    if args.guide:
        print("\n" + "-" * 70)
        print("  2. FROM THE GUIDE PRICE")
        print("-" * 70)
        print(f"    guide £{args.guide:,}  x1.20 typical  = £{args.guide*1.20:,.0f}")
        print(f"    usual band 1.10-1.49x  = £{args.guide*1.10:,.0f} - "
              f"£{args.guide*1.49:,.0f}")
        print("    (measured on 120 Staffordshire lots; only 5% sell at or below guide)")

    # ---- 3. comparable auctions -------------------------------------------
    lots = []
    for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
        f = DATA / f"{p}.jsonl"
        if f.exists():
            lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
    out = pc.split()[0]
    near = [l for l in lots if l["hammer_price"]
            and l.get("property_type") == args.type
            and (l.get("postcode") or "").startswith(out)]
    print("\n" + "-" * 70)
    print("  3. COMPARABLE AUCTION SALES")
    print("-" * 70)
    comp_lo = comp_hi = comp_med = None
    if len(near) >= 5:
        a = np.array(sorted(l["hammer_price"] for l in near))
        comp_lo, comp_med, comp_hi = (np.percentile(a, 25), np.percentile(a, 50),
                                      np.percentile(a, 75))
        print(f"    {len(a)} sales in {out}: £{comp_lo:,.0f} - £{comp_hi:,.0f}, "
              f"median £{comp_med:,.0f}")
    else:
        print(f"    only {len(near)} auction sales of this type in {out} — too few")

    # ---- verdict -----------------------------------------------------------
    print("\n" + "=" * 70)
    print("  WHAT TO DO")
    print("=" * 70)
    # Reconcile the three. Where they overlap is worth far more than any one.
    lows = [lo50] + ([args.guide * 1.10] if args.guide else []) + \
           ([comp_lo] if comp_lo else [])
    highs = [hi50] + ([args.guide * 1.49] if args.guide else []) + \
            ([comp_hi] if comp_hi else [])
    ov_lo, ov_hi = max(lows), min(highs)
    print(f"    model            £{lo50:,.0f} - £{hi50:,.0f}")
    if args.guide:
        print(f"    guide implies    £{args.guide*1.10:,.0f} - £{args.guide*1.49:,.0f}"
              f"   (typical £{args.guide*1.20:,.0f})")
    if comp_lo:
        print(f"    comparables      £{comp_lo:,.0f} - £{comp_hi:,.0f}")
    if ov_lo <= ov_hi:
        print(f"\n    ALL AGREE ON     £{ov_lo:,.0f} - £{ov_hi:,.0f}   <- bid here")
        print(f"    walk away above  £{ov_hi:,.0f}")
    else:
        print("\n    THE THREE DO NOT OVERLAP.")
        print("    That usually means the lot is unusual, the guide is bait, or the")
        print("    local sample is too thin. Read the legal pack; do not average them.")
        print(f"    widest span      £{min(lows):,.0f} - £{max(highs):,.0f}")
    print("\n    Hammer only — buyer's fees and any works are on top.")
    print("    This prices an ORDINARY lot. It cannot see condition, tenure or")
    print("    title problems, which is where the remaining error lives.")
    print("=" * 70)


if __name__ == "__main__":
    main()
