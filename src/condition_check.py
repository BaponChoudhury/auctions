"""Is 'condition adds nothing' a real finding, or just poor coverage?"""
import numpy as np
import pandas as pd

df = pd.read_csv("../data/features.csv")
df = df[df.hammer_price > 1000]
df["comp_median_n"] = pd.to_numeric(df.comp_median, errors="coerce")
df["ratio"] = df.hammer_price / df.comp_median_n

print("condition label coverage across the modelling table:")
print(df.condition.value_counts().to_string())
known = df[df.condition != "unknown"]
print(f"\nlots with a NON-unknown condition: {len(known):,} of {len(df):,} "
      f"({100*len(known)//len(df)}%)")

print("\ncondition coverage by source (descriptions were only fetched for some):")
for src, sub in df.groupby("source"):
    n = (sub.condition != "unknown").sum()
    print(f"  {src:11} {n:5,}/{len(sub):5,}  {100*n//len(sub):3}% classified")

print("\nDOES condition move the price, on lots where we actually know it?")
print(f"  {'condition':14} {'n':>6} {'median hammer/comp':>20}")
res = known[known.property_type.isin(["D", "S", "T", "F"])]
for c, sub in res.groupby("condition"):
    rr = sub.ratio.dropna()
    if len(rr) < 20:
        continue
    print(f"  {c:14} {len(rr):6,} {np.median(rr):19.2f}")
base = res[res.condition == "ready"].ratio.dropna()
full = res[res.condition == "full_refurb"].ratio.dropna()
if len(base) > 20 and len(full) > 20:
    print(f"\n  ready vs full_refurb: {np.median(base):.2f} vs {np.median(full):.2f} "
          f"-> refurb lots sell for {100*(1-np.median(full)/np.median(base)):.0f}% "
          f"less relative to their neighbourhood")
