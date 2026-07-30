"""Re-score the condition classifier against the cached 60-lot corpus."""
import collections, json, sys
sys.path.insert(0, "../src")
from enrich import classify_condition

rows = json.load(open("sampled.json", encoding="utf-8"))
counts = collections.Counter()
for r in rows:
    cls, _ = classify_condition(r["description"])
    counts[cls] += 1
    if cls != "unknown":
        d = " ".join(r["description"].split())
        print(f"{cls:12} {d[:110]}")
print(f"\n{dict(counts)}   ({len(rows)} lots, "
      f"{100*(len(rows)-counts['unknown'])//len(rows)}% classified)")
