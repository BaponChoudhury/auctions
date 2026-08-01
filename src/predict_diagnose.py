"""Why is auction price hard to predict, and is it hard for ALL lots equally?

Three questions:
  1. How well does a neighbourhood comp track an auction price at all?
  2. Does the model do better on ordinary houses than on land/commercial?
  3. Which features actually earn their place?
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from predict_price import CAT, NUM, prep

df = pd.read_csv("../data/features.csv")
df = df[df.hammer_price > 1000].sort_values("auction_date")
df["comp_median_n"] = pd.to_numeric(df.comp_median, errors="coerce")
df["ratio"] = df.hammer_price / df.comp_median_n

print("=== 1. auction price vs the neighbourhood's normal sold prices ===")
r = df.ratio.dropna()
for q in (10, 25, 50, 75, 90):
    print(f"  p{q:<3} hammer / neighbourhood median = {np.percentile(r, q):.2f}")
print(f"  a lot sells BELOW the local median {100*(r < 1).mean():.0f}% of the time")
print("  (spread this wide is why the comp alone cannot price a lot)")

print("\n  by property type:")
for t, sub in df.groupby(df.property_type.fillna("?")):
    rr = sub.ratio.dropna()
    if len(rr) < 100:
        continue
    print(f"    {t:3} n={len(rr):5,}  median ratio {np.median(rr):.2f}  "
          f"p10-p90 {np.percentile(rr,10):.2f}-{np.percentile(rr,90):.2f}")

dates = df.auction_date.tolist()
split = dates[int(len(dates) * 0.8)]
train, test = df[df.auction_date < split], df[df.auction_date >= split]


def fit_score(tr, te, use_guide=False, feats=None):
    X_tr, _ = prep(tr, use_guide)
    X_te, _ = prep(te, use_guide)
    if feats:
        X_tr, X_te = X_tr[feats], X_te[feats]
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, max_depth=6,
                                      categorical_features="from_dtype", random_state=0)
    m.fit(X_tr, np.log(tr.hammer_price.values))
    pred = np.exp(m.predict(X_te))
    ape = np.abs(pred - te.hammer_price.values) / te.hammer_price.values * 100
    return np.median(ape), (ape <= 20).mean() * 100, m, X_te


print("\n=== 2. accuracy by segment (no guide price) ===")
print(f"  {'segment':28} {'train':>7} {'test':>6} {'MdAPE':>7} {'within20%':>10}")
RESI = ["D", "S", "T", "F"]
segs = {
    "all lots": (train, test),
    "residential only (D/S/T/F)": (train[train.property_type.isin(RESI)],
                                   test[test.property_type.isin(RESI)]),
    "houses only (D/S/T)": (train[train.property_type.isin(["D", "S", "T"])],
                            test[test.property_type.isin(["D", "S", "T"])]),
    "land / commercial (O)": (train[train.property_type == "O"],
                              test[test.property_type == "O"]),
}
for name, (tr, te) in segs.items():
    if len(tr) < 200 or len(te) < 50:
        print(f"  {name:28} too few rows")
        continue
    mdape, w20, _, _ = fit_score(tr, te)
    print(f"  {name:28} {len(tr):7,} {len(te):6,} {mdape:6.1f}% {w20:9.1f}%")

print("\n=== 3. which features earn their place (residential, no guide) ===")
tr = train[train.property_type.isin(RESI)]
te = test[test.property_type.isin(RESI)]
mdape, w20, model, X_te = fit_score(tr, te)
imp = permutation_importance(model, X_te, np.log(te.hammer_price.values),
                             n_repeats=5, random_state=0, scoring="r2")
order = np.argsort(imp.importances_mean)[::-1]
for i in order:
    print(f"  {X_te.columns[i]:16} {imp.importances_mean[i]:+.4f}")
