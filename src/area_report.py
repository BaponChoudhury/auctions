"""What does the auction market look like in one place, and can we price it?

Practical use: point it at a local authority and it tells you what sells, what
the normal auction discount is there, which postcode sectors have the deepest
discounts, which properties keep coming back unsold, and - importantly - how
accurate the price model actually is in that specific area, so you know how much
to trust it locally.

  python area_report.py --area Birmingham
  python area_report.py --area "Stoke-on-Trent" --type T
"""

import argparse
import collections
import json
import pathlib
import statistics
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache

RESI = ("D", "S", "T", "F")
TYPE_NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat",
             "O": "Land/commercial"}
SOLD = ("sold", "sold_prior", "sold_after")


def money(n):
    return f"£{n:,.0f}" if n is not None and not pd.isna(n) else "—"


def load(area: str):
    geo = load_cache()
    rows = []
    for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
        f = pathlib.Path(__file__).parent.parent / "data" / f"{p}.jsonl"
        if f.exists():
            rows += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
    out = []
    for l in rows:
        g = geo.get(l.get("postcode") or "") or {}
        if (g.get("admin_district") or "").lower() != area.lower():
            continue
        l["district"] = g.get("admin_district")
        out.append(l)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True)
    ap.add_argument("--type", help="Restrict to a PPD type code (D/S/T/F/O)")
    ap.add_argument("--features", default="../data/features.csv")
    args = ap.parse_args()

    lots = load(args.area)
    if not lots:
        sys.exit(f"No lots found for {args.area!r}. Try a local-authority name, "
                 f"e.g. Birmingham, 'Stoke-on-Trent', Stafford, Walsall.")
    if args.type:
        lots = [l for l in lots if l.get("property_type") == args.type]

    sold = [l for l in lots if l["hammer_price"]]
    print("=" * 66)
    print(f"  {args.area.upper()}   {len(lots):,} lots   {len(sold):,} with a sale price")
    print("=" * 66)
    if len(sold) < 15:
        print("\n  ** Very thin data here. Treat everything below as indicative. **")

    dates = [l["auction_date"] for l in lots if l["auction_date"]]
    print(f"\nperiod: {min(dates)} to {max(dates)}")
    st = collections.Counter(l["status"] for l in lots)
    total_sold = sum(st[s] for s in SOLD)
    print(f"sell-through: {total_sold:,}/{len(lots):,} "
          f"({100*total_sold//len(lots)}% sold in some form)")
    print(f"  {dict(st.most_common())}")

    # --- what things go for -------------------------------------------------
    print("\n" + "-" * 66)
    print("WHAT SELLS, AND FOR HOW MUCH")
    print("-" * 66)
    print(f"  {'type':16} {'sold':>5} {'median':>10} {'p25-p75':>21}")
    by_type = collections.defaultdict(list)
    for l in sold:
        by_type[l.get("property_type") or "?"].append(l["hammer_price"])
    for t, prices in sorted(by_type.items(), key=lambda x: -len(x[1])):
        if len(prices) < 3:
            continue
        prices.sort()
        p25 = prices[len(prices) // 4]
        p75 = prices[3 * len(prices) // 4]
        print(f"  {TYPE_NAME.get(t, t):16} {len(prices):5,} "
              f"{money(statistics.median(prices)):>10} "
              f"{money(p25) + ' - ' + money(p75):>21}")

    # --- the discount -------------------------------------------------------
    try:
        df = pd.read_csv(args.features)
    except FileNotFoundError:
        df = None
    if df is not None:
        df = df[(df.district.astype(str).str.lower() == args.area.lower())
                & (df.hammer_price > 1000)].copy()
        if args.type:
            df = df[df.property_type == args.type]
        df["comp_n"] = pd.to_numeric(df.comp_median, errors="coerce")
        df["ratio"] = df.hammer_price / df.comp_n
        r = df.ratio.replace([np.inf, -np.inf], np.nan).dropna()
        if len(r) >= 10:
            print("\n" + "-" * 66)
            print("AUCTION DISCOUNT vs NORMAL LOCAL SALES")
            print("-" * 66)
            print(f"  typical lot sells at {r.median():.2f}x the local going rate")
            print(f"  i.e. about {100*(1-r.median()):.0f}% below normal open-market price")
            print(f"  range: {r.quantile(.25):.2f}x (cheap quartile) to "
                  f"{r.quantile(.75):.2f}x (dear quartile)")
            print(f"  -> anything above {r.quantile(.75):.2f}x is dear FOR AN AUCTION here")

            # Where the deepest discounts are.
            sect = collections.defaultdict(list)
            for _, row in df.iterrows():
                if not pd.isna(row.ratio) and row.sector:
                    sect[row.sector].append(row.ratio)
            good = [(s, statistics.median(v), len(v))
                    for s, v in sect.items() if len(v) >= 8]
            if good:
                good.sort(key=lambda x: x[1])
                print(f"\n  postcode sectors with the DEEPEST typical discount "
                      f"(min 8 sales):")
                print(f"    {'sector':10} {'lots':>5} {'typical vs local':>18}")
                for s, m, n in good[:6]:
                    print(f"    {s:10} {n:5} {m:17.2f}x")

    # --- distressed / repeat ------------------------------------------------
    keys = collections.Counter(l["property_key"] for l in lots if l["property_key"])
    repeat = {k: n for k, n in keys.items() if n > 1}
    if repeat:
        print("\n" + "-" * 66)
        print("PROPERTIES OFFERED MORE THAN ONCE  (the stale/distressed signal)")
        print("-" * 66)
        print(f"  {len(repeat):,} properties came back to auction at least twice")
        for k, n in sorted(repeat.items(), key=lambda x: -x[1])[:6]:
            ex = [l for l in lots if l["property_key"] == k]
            ex.sort(key=lambda l: l["auction_date"] or "")
            last = ex[-1]
            print(f"    {n}x  {ex[0]['address_raw'][:44]:46} "
                  f"last: {last['status']:11} {money(last['hammer_price'])}")

    # --- how much to trust the model here -----------------------------------
    if df is not None and len(df) >= 120:
        print("\n" + "-" * 66)
        print("HOW ACCURATE IS THE PRICE MODEL *HERE*")
        print("-" * 66)
        d = df.sort_values("auction_date")
        NUM = ["comp_median", "comp_count", "comp_iqr", "bedrooms",
               "flag_tenanted", "flag_hmo", "flag_land"]
        X = d[NUM].apply(pd.to_numeric, errors="coerce")
        X["property_type"] = d.property_type.astype("category")
        X = X[[c for c in X.columns if X[c].nunique(dropna=True) >= 2]]
        cut = int(len(d) * 0.75)
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06,
                                          max_depth=5, random_state=0,
                                          categorical_features="from_dtype")
        m.fit(X.iloc[:cut], np.log(d.hammer_price.values[:cut]))
        pred = np.exp(m.predict(X.iloc[cut:]))
        actual = d.hammer_price.values[cut:]
        ape = np.abs(pred - actual) / actual * 100
        print(f"  tested on {len(actual)} later sales in this area")
        print(f"  half of predictions land within {np.median(ape):.0f}%")
        print(f"  {(ape <= 20).mean()*100:.0f}% land within 20%")
        typical = statistics.median(actual)
        print(f"  on a {money(typical)} property that is about "
              f"±{money(typical * np.median(ape) / 100)}")
        print("\n  Use it to shortlist. Do not set your ceiling from it.")

    print("\n" + "=" * 66)


if __name__ == "__main__":
    main()
