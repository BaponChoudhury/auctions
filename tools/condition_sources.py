"""Where can condition still be measured WITHOUT fetching more pages?"""
import collections, json, re, sys
sys.path.insert(0, "../src")
from enrich import classify_condition

print("=== Clive Emson lot headings (already scraped, 3,880 lots) ===")
rows = [json.loads(l) for l in open("../data/emson_all.jsonl", encoding="utf-8") if l.strip()]
hit = sum(1 for r in rows if classify_condition(r["description"])[0] != "unknown")
print(f"current classifier fires on {hit}/{len(rows)} ({100*hit//len(rows)}%)")
print("\nheadings containing condition-ish words the classifier may be missing:")
CUE = r"(improve|modernis|refurb|renovat|repair|updat|potential|develop|"
CUE += r"scope|投|dilapidat|derelict|require|need)"
tally = collections.Counter()
for r in rows:
    for m in re.finditer(CUE, r["description"], re.I):
        tally[m.group(1).lower()] += 1
for w, n in tally.most_common(12):
    print(f"  {n:5}  {w}")
print("\nsample headings:")
for r in rows[:14]:
    print(f"  {r['description'][:78]}")

print("\n=== Allsop RESIDENTIAL descriptions (commercial ones had no condition copy) ===")
al = [json.loads(l) for l in open("../data/allsop_all.jsonl", encoding="utf-8") if l.strip()]
resi = [r for r in al if r.get("property_type") in ("D", "S", "T", "F")]
hit = sum(1 for r in resi if classify_condition(r["description"])[0] != "unknown")
print(f"residential lots: {len(resi):,}, classifier fires on {hit}")
for r in resi[:6]:
    print(f"  - {r['description'][:150]}")
