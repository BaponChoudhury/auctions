"""Can area + condition + neighbourhood prices predict the auction sale price?

Evaluated honestly:
  * TIME-BASED split — train on older auctions, test on later ones. A random
    split would let the model see the future and flatter itself.
  * Every feature is knowable BEFORE the hammer falls.
  * Compared against dumb baselines. A model that cannot beat "just use the
    neighbourhood median" is not worth building.

Metric is median absolute percentage error (MdAPE) plus hit rates within ±10/20%.
Mean error is useless here: a handful of £2m lots dominate it.

  python predict_price.py --features ../data/features.csv
"""

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error


def score(name, y_true, y_pred, out):
    mask = np.isfinite(y_pred) & (y_pred > 0)
    if mask.sum() == 0:
        out.append((name, 0, None, None, None, None))
        return
    yt, yp = y_true[mask], y_pred[mask]
    ape = np.abs(yp - yt) / yt * 100
    out.append((name, int(mask.sum()), float(np.median(ape)),
                float(np.mean(np.abs(yp - yt))),
                float((ape <= 10).mean() * 100), float((ape <= 20).mean() * 100)))


def report(rows):
    print(f"\n{'model':38} {'n':>6} {'MdAPE':>7} {'MAE':>10} "
          f"{'within10%':>10} {'within20%':>10}")
    for name, n, mdape, mae, w10, w20 in rows:
        if mdape is None:
            print(f"{name:38} {n:6} {'-':>7}")
            continue
        print(f"{name:38} {n:6} {mdape:6.1f}% £{mae:9,.0f} "
              f"{w10:9.1f}% {w20:9.1f}%")


CAT = ["source", "property_type", "region", "district", "condition"]
NUM = ["guide_price", "bedrooms", "comp_median", "comp_count", "comp_iqr",
       "flag_tenanted", "flag_hmo", "flag_land",
       # EPC: floor area, and the comp expressed per square metre. The model is
       # ~94% driven by comp_median, so sharpening that one feature is where the
       # remaining accuracy is most likely to be.
       "floor_area_m2", "comp_per_m2"]


def prep(df, use_guide):
    cols = [c for c in NUM if c in df.columns]
    if not use_guide:
        cols = [c for c in cols if c != "guide_price"]
    X = df[cols].apply(pd.to_numeric, errors="coerce").copy()
    for c in CAT:
        if c in df.columns:
            X[c] = df[c].astype("category")
    # A column with no variation breaks the histogram binner and carries nothing.
    usable = [c for c in X.columns if X[c].nunique(dropna=True) >= 2]
    return X[usable], usable


def run(df, label, use_guide, split_date):
    train, test = df[df.auction_date < split_date], df[df.auction_date >= split_date]
    if len(test) < 50 or len(train) < 200:
        print(f"\n{label}: not enough data (train {len(train)}, test {len(test)})")
        return
    print(f"\n=== {label} ===")
    print(f"train {len(train):,} lots (to {split_date}), test {len(test):,} lots (after)")

    y_tr, y_te = train.hammer_price.values, test.hammer_price.values
    rows = []

    # Baseline 1: the neighbourhood median itself.
    score("baseline: neighbourhood median", y_te,
          pd.to_numeric(test.comp_median, errors="coerce").values, rows)

    # Baseline 2: the guide price, where the house publishes one.
    if use_guide:
        score("baseline: guide price", y_te,
              pd.to_numeric(test.guide_price, errors="coerce").values, rows)

    # Baseline 3: median sale price of the training set (constant).
    score("baseline: global median", y_te,
          np.full(len(y_te), np.median(y_tr), dtype=float), rows)

    X_tr, cols = prep(train, use_guide)
    X_te = prep(test, use_guide)[0].reindex(columns=cols)
    # Log target: prices are lognormal and this stops £2m lots dominating.
    model = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.06, max_depth=6,
        categorical_features="from_dtype", random_state=0)
    model.fit(X_tr, np.log(y_tr))
    score("gradient boosting", y_te, np.exp(model.predict(X_te)), rows)
    report(rows)
    return model


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="../data/features.csv")
    ap.add_argument("--split", default=None,
                    help="ISO date; default = 80th percentile of auction dates")
    args = ap.parse_args()

    df = pd.read_csv(args.features)
    df = df[df.hammer_price > 1000]          # drop nominal-price lots
    df = df.sort_values("auction_date")
    # 80th percentile by position — auction_date is an ISO string, so ordering
    # works but arithmetic quantiles do not.
    dates = df.auction_date.tolist()
    split = args.split or dates[int(len(dates) * 0.8)]
    print(f"lots with a known sale price: {len(df):,}  "
          f"({df.auction_date.min()} to {df.auction_date.max()})")

    run(df, "ALL LOTS — no guide price used (works for every house)",
        use_guide=False, split_date=split)

    g = df[pd.to_numeric(df.guide_price, errors="coerce").notna()]
    run(g, "LOTS WITH A PUBLISHED GUIDE (SDL + Allsop only)",
        use_guide=True, split_date=split)


if __name__ == "__main__":
    main()
