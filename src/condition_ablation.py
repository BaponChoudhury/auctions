"""Does knowing a lot's condition improve the price prediction?

Tested where condition coverage is actually real (Clive Emson, 31% classified),
with a time-based split and an ablation: same model, same rows, condition
feature in vs out. Anything else confounds coverage with signal.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

CAT = ["source", "property_type", "region", "district"]
NUM = ["bedrooms", "comp_median", "comp_count", "comp_iqr",
       "flag_tenanted", "flag_hmo", "flag_land"]


def prep(df, with_condition, keep=None):
    X = df[NUM].apply(pd.to_numeric, errors="coerce").copy()
    for c in CAT:
        X[c] = df[c].astype("category")
    if with_condition:
        X["condition"] = df["condition"].astype("category")
        X["needs_work"] = (df["condition"]
                           .isin(["full_refurb", "light_refurb", "structural"])
                           .astype(int))
    if keep is not None:
        return X[keep]
    # A column with no variation (Emson records no bedrooms, some flags are all
    # zero in a subset) breaks the histogram binner and carries no information.
    usable = [c for c in X.columns if X[c].nunique(dropna=True) >= 2]
    return X[usable]


def evaluate(train, test, with_condition, seeds=(0, 1, 2)):
    X_tr = prep(train, with_condition)
    apes = []
    for s in seeds:
        m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06,
                                          max_depth=6, random_state=s,
                                          categorical_features="from_dtype")
        m.fit(X_tr, np.log(train.hammer_price.values))
        pred = np.exp(m.predict(prep(test, with_condition, keep=X_tr.columns)))
        apes.append(np.abs(pred - test.hammer_price.values) / test.hammer_price.values * 100)
    ape = np.mean(apes, axis=0)
    return np.median(ape), (ape <= 20).mean() * 100


df = pd.read_csv("../data/features.csv")
df = df[df.hammer_price > 1000].sort_values("auction_date")

print("condition coverage by source (priced lots):")
for src, sub in df.groupby("source"):
    n = (sub.condition != "unknown").sum()
    print(f"  {src:11} {n:5,}/{len(sub):5,}  {100*n/len(sub):4.1f}%")

RESI = ["D", "S", "T", "F"]
SETS = {
    "Clive Emson, all lots": df[df.source == "emson"],
    "Clive Emson, residential": df[(df.source == "emson") & df.property_type.isin(RESI)],
    "All sources, residential": df[df.property_type.isin(RESI)],
}

print(f"\n{'dataset':30} {'train':>6} {'test':>6} {'no cond':>9} "
      f"{'+cond':>8} {'change':>8}")
for name, sub in SETS.items():
    sub = sub.sort_values("auction_date")
    if len(sub) < 400:
        print(f"{name:30} too few rows ({len(sub)})")
        continue
    dates = sub.auction_date.tolist()
    split = dates[int(len(dates) * 0.75)]
    tr, te = sub[sub.auction_date < split], sub[sub.auction_date >= split]
    if len(tr) < 200 or len(te) < 80:
        print(f"{name:30} split too small")
        continue
    base, _ = evaluate(tr, te, False)
    cond, _ = evaluate(tr, te, True)
    print(f"{name:30} {len(tr):6,} {len(te):6,} {base:8.1f}% {cond:7.1f}% "
          f"{cond-base:+7.1f}pp")

# Direct effect, controlling for property type and area band.
print("\ndirect effect: hammer / neighbourhood median, Emson residential only")
e = df[(df.source == "emson") & df.property_type.isin(RESI)].copy()
e["comp_n"] = pd.to_numeric(e.comp_median, errors="coerce")
e["ratio"] = e.hammer_price / e.comp_n
e["needs_work"] = e.condition.isin(["full_refurb", "light_refurb", "structural"])
print(f"  {'type':6} {'needs work':>12} {'n':>6} {'median ratio':>13}")
for t, sub in e.groupby("property_type"):
    for flag, s2 in sub.groupby("needs_work"):
        r = s2.ratio.dropna()
        if len(r) < 25:
            continue
        print(f"  {t:6} {str(flag):>12} {len(r):6,} {np.median(r):12.2f}")
