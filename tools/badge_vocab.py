"""What condition/tenure signal is already sitting unused in result_raw?"""
import collections, json, re, sys

for path in ("../data/bw_full.jsonl", "../data/emson_all.jsonl",
             "../data/allsop_all.jsonl"):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    src = rows[0]["source"]
    print(f"\n=== {src}  ({len(rows):,} lots)")
    tally = collections.Counter()
    for r in rows:
        parts = [p.strip() for p in (r.get("result_raw") or "").split(";")]
        for p in parts[1:]:          # first part is the status/price
            if p:
                tally[p] += 1
    for label, n in tally.most_common(18):
        print(f"  {n:6,}  {label[:66]}")

print("\n=== what Allsop descriptions actually look like ===")
rows = [json.loads(l) for l in open("../data/allsop_all.jsonl", encoding="utf-8") if l.strip()]
sys.path.insert(0, "../src")
from enrich import classify_condition
hit = [r for r in rows if classify_condition(r["description"])[0] != "unknown"]
print(f"classifier fires on {len(hit)}/{len(rows)}")
print("\nsample descriptions it does NOT classify:")
for r in [r for r in rows if classify_condition(r["description"])[0] == "unknown"][:8]:
    print(f"  - {r['description'][:150]}")
