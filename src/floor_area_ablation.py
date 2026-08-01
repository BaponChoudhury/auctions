"""Does EPC floor area improve the price prediction?

Tested the same way as the condition hypothesis: identical rows, identical model,
feature in vs out, time-based split. Restricted to lots that HAVE a floor area,
otherwise the comparison confounds coverage with signal.

  python floor_area_ablation.py --features ../data/features.csv
"""

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

CAT = ["source", "property_type", "region", "district", "condition"]
BASE_NUM = ["bedrooms", "comp_median", "comp_count", "comp_iqr",
            "flag_tenanted", "flag_hmo", "flag_land"]
EPC_NUM = ["floor_area_m2", "comp_per_m2"]


def prep(df, cols_num, keep=None):
    X = df[cols_num].apply(pd.to_numeric, errors="coerce").copy()
    for c in CAT:
        X[c] = df[c].astype("category")
    if keep is not None:
        return X.reindex(columns=keep)
    usable = [c for c in X.columns if X[c].nunique(dropna=True) >= 2]
    return X[usable]


def evaluate(train, test, cols_num, seeds=(0, 1, 2)):
    X_tr = prep(train, cols_num)
    X_te = prep(test, cols_num, keep=X_tr.columns)
    apes = []
    for s in seeds:
        m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06,
                                          max_depth=6, random_state=s,
                                          categorical_features="from_dtype")
        m.fit(X_tr, np.log(train.hammer_price.values))
        pred = np.exp(m.predict(X_te))
        apes.append(np.abs(pred - test.hammer_price.values)
                    / test.hammer_price.values * 100)
    ape = np.mean(apes, axis=0)
    return np.median(ape), (ape <= 20).mean() * 100


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="../data/features.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.features)
    df = df[df.hammer_price > 1000].sort_values("auction_date")
    df["area_n"] = pd.to_numeric(df.get("floor_area_m2"), errors="coerce")

    have = df[df.area_n.notna()]
    print(f"lots with a known sale price : {len(df):,}")
    print(f"lots with an EPC floor area  : {len(have):,} "
          f"({100*len(have)//len(df)}%)")
    print("\ncoverage by source:")
    for src, sub in df.groupby("source"):
        n = sub.area_n.notna().sum()
        print(f"  {src:11} {n:5,}/{len(sub):5,}  {100*n/len(sub):4.1f}%")

    if len(have) < 400:
        print("\nnot enough floor-area rows yet")
        return

    print(f"\nfloor area: median {have.area_n.median():.0f} m2, "
          f"p10-p90 {have.area_n.quantile(.1):.0f}-{have.area_n.quantile(.9):.0f}")
    ppm = pd.to_numeric(have.comp_per_m2, errors="coerce").dropna()
    if len(ppm):
        print(f"neighbourhood comp per m2: median £{ppm.median():,.0f}, "
              f"p10-p90 £{ppm.quantile(.1):,.0f}-£{ppm.quantile(.9):,.0f}")

    RESI = ["D", "S", "T", "F"]
    SETS = {
        "lots with a floor area": have,
        "  of those, residential": have[have.property_type.isin(RESI)],
        "  of those, houses only": have[have.property_type.isin(["D", "S", "T"])],
    }
    print(f"\n{'dataset':28} {'train':>6} {'test':>6} {'no EPC':>8} "
          f"{'+EPC':>7} {'change':>8}")
    for name, sub in SETS.items():
        sub = sub.sort_values("auction_date")
        if len(sub) < 300:
            print(f"{name:28} too few rows ({len(sub)})")
            continue
        dates = sub.auction_date.tolist()
        split = dates[int(len(dates) * 0.75)]
        tr, te = sub[sub.auction_date < split], sub[sub.auction_date >= split]
        if len(tr) < 200 or len(te) < 60:
            print(f"{name:28} split too small")
            continue
        base, _ = evaluate(tr, te, BASE_NUM)
        epc, _ = evaluate(tr, te, BASE_NUM + EPC_NUM)
        print(f"{name:28} {len(tr):6,} {len(te):6,} {base:7.1f}% "
              f"{epc:6.1f}% {epc-base:+7.1f}pp")

    # Is price per square metre a tighter quantity than price per property?
    h = have[have.property_type.isin(RESI)].copy()
    h["ppm_actual"] = h.hammer_price / h.area_n
    h["comp_n"] = pd.to_numeric(h.comp_median, errors="coerce")
    print("\nspread of the thing we are trying to predict (residential):")
    for label, series in (("hammer / comp_median", h.hammer_price / h.comp_n),
                          ("hammer per m2 (£)", h.ppm_actual)):
        s = series.replace([np.inf, -np.inf], np.nan).dropna()
        if len(s) < 50:
            continue
        cv = s.std() / s.mean()
        print(f"  {label:22} median {s.median():>9,.0f}  "
              f"p10-p90 {s.quantile(.1):>8,.0f}-{s.quantile(.9):>9,.0f}  "
              f"CV {cv:.2f}")


if __name__ == "__main__":
    main()
