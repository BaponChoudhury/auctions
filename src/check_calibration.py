"""Is the model equally trustworthy across price bands and types?

Prompted by Cherry Arbour: the model said GBP 318k where the comparable method
said GBP 233k. One of them is wrong and it matters which.
"""

import pathlib
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from predict_lot import CATS, FEATURES

DATA = pathlib.Path(__file__).parent.parent / "data"
NAME = {"D": "Detached", "S": "Semi", "T": "Terraced", "F": "Flat"}

df = pd.read_csv(DATA / "features.csv")
df = df[(df.hammer_price > 1000) & df.property_type.isin(list(NAME))]
df = df.sort_values("auction_date")
cut = int(len(df) * 0.8)
tr, te = df.iloc[:cut].copy(), df.iloc[cut:].copy()


def prep(d):
    X = d[FEATURES].apply(pd.to_numeric, errors="coerce").copy()
    for c in CATS:
        X[c] = d[c].astype("category")
    return X


m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, max_depth=6,
                                  random_state=0, categorical_features="from_dtype")
m.fit(prep(tr), np.log(tr.hammer_price.values))
te["pred"] = np.exp(m.predict(prep(te)))
te["ape"] = (te.pred - te.hammer_price).abs() / te.hammer_price * 100
te["bias"] = te.pred / te.hammer_price

print("=" * 70)
print("  CALIBRATION BY ACTUAL SALE PRICE")
print("=" * 70)
print(f"  {'band':18} {'n':>5} {'median err':>11} {'median bias':>12}")
bands = [(0, 50_000), (50_000, 100_000), (100_000, 200_000),
         (200_000, 400_000), (400_000, 10_000_000)]
for lo, hi in bands:
    s = te[(te.hammer_price >= lo) & (te.hammer_price < hi)]
    if len(s) < 20:
        continue
    label = f"£{lo//1000}k-£{hi//1000}k" if hi < 10_000_000 else f"£{lo//1000}k+"
    print(f"  {label:18} {len(s):5} {s.ape.median():10.0f}% "
          f"{s.bias.median():11.2f}x")
print("\n  bias > 1.00 = model predicts HIGHER than reality")

print("\n" + "=" * 70)
print("  CALIBRATION BY TYPE")
print("=" * 70)
print(f"  {'type':12} {'n':>5} {'median err':>11} {'median bias':>12}")
for t, s in te.groupby("property_type"):
    if len(s) < 20:
        continue
    print(f"  {NAME[t]:12} {len(s):5} {s.ape.median():10.0f}% "
          f"{s.bias.median():11.2f}x")

print("\n" + "=" * 70)
print("  HOW MUCH TRAINING DATA IS THERE ABOVE £250k?")
print("=" * 70)
for lo in (250_000, 400_000):
    n = (tr.hammer_price >= lo).sum()
    print(f"  training lots >= £{lo//1000}k: {n:,} of {len(tr):,} "
          f"({100*n/len(tr):.1f}%)")
print("\n  A model trained mostly on sub-£250k stock should not be trusted to")
print("  price an expensive detached house - there is little to learn from.")

print("\n" + "=" * 70)
print("  SANITY CHECK: hammer as a fraction of the local comp")
print("=" * 70)
te["comp_n"] = pd.to_numeric(te.comp_median, errors="coerce")
te["ratio_actual"] = te.hammer_price / te.comp_n
te["ratio_pred"] = te.pred / te.comp_n
for t, s in te.groupby("property_type"):
    s = s.dropna(subset=["ratio_actual", "ratio_pred"])
    if len(s) < 20:
        continue
    print(f"  {NAME[t]:12} actual {s.ratio_actual.median():.2f}x   "
          f"predicted {s.ratio_pred.median():.2f}x")
print("=" * 70)
