"""Are unsold-lot matches false positives, or genuine later private sales?
And where do the non-exact price agreements come from?"""
import collections, json, statistics, sys

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
m = [r for r in rows if r.get("recovered_price") is not None]
print(f"matched lots: {len(m):,}")

SOLD = ("sold", "sold_prior", "sold_after")
print(f"\n{'status':12} {'n':>6} {'median lag':>11} {'p10':>6} {'p90':>6} {'lag<45d':>9}")
for st in sorted({r["status"] for r in m}):
    sub = [r for r in m if r["status"] == st]
    lags = sorted(r["recovered_lag_days"] for r in sub)
    near = sum(1 for l in lags if l < 45)
    print(f"{st:12} {len(sub):6,} {statistics.median(lags):11.0f} "
          f"{lags[len(lags)//10]:6} {lags[9*len(lags)//10]:6} "
          f"{100*near//len(lags):8}%")

print("\nInterpretation check: a lot that did NOT sell at auction but completed")
print("within the normal 20-28 day window is suspicious; one completing months")
print("later is most likely a genuine post-auction private sale.")

# Price agreement, where both figures are known.
both = [r for r in m if r.get("hammer_price")]
diffs = [r["recovered_price"] - r["hammer_price"] for r in both]
print(f"\nprice agreement on {len(both):,} lots with a published hammer price:")
buckets = collections.Counter()
for d in diffs:
    if d == 0:
        buckets["exact"] += 1
    elif abs(d) <= 1000:
        buckets["within £1k"] += 1
    elif d > 0:
        buckets["PPD higher"] += 1
    else:
        buckets["PPD lower"] += 1
for k, n in buckets.most_common():
    print(f"  {k:12} {n:6,} ({100*n//len(diffs):3}%)")

nz = [d for d in diffs if d != 0]
if nz:
    nz.sort()
    print(f"\n  non-exact differences: median £{statistics.median(nz):,.0f}, "
          f"p10 £{nz[len(nz)//10]:,}, p90 £{nz[9*len(nz)//10]:,}")
    print("  examples:")
    for r in [x for x in both if x["recovered_price"] != x["hammer_price"]][:6]:
        print(f"    hammer £{r['hammer_price']:>9,}  ppd £{r['recovered_price']:>9,}  "
              f"lag {r['recovered_lag_days']:>4}d  {r['address_raw'][:44]}")

# Ambiguity: more than one PPD sale in the window is a false-positive risk.
multi = [r for r in m if r.get("ppd_matches", 0) > 1]
print(f"\nlots with MORE THAN ONE candidate sale in the window: {len(multi):,} "
      f"({100*len(multi)//len(m)}%) — each is an ambiguous match")
