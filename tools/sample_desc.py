"""Sample real lot descriptions to build/validate the condition ruleset."""
import collections, json, re, sys
sys.path.insert(0, "../src")
from scrape_sdl import fetch_description
from enrich import classify_condition

n = int(sys.argv[1])
rows = [json.loads(l) for l in open("lots_1267.jsonl", encoding="utf-8")][:n]
for r in rows:
    r["description"] = fetch_description(r["lot_url"])
json.dump(rows, open("sampled.json", "w", encoding="utf-8"), indent=1)

counts = collections.Counter(classify_condition(r["description"])[0] for r in rows)
print("classifier:", dict(counts), f"  ({n} lots)")

# What condition wording actually appears? Pull the clause around each cue word.
CUES = r"(modernis|renovat|refurbish|repair|upgrad|improve|condition|presented|" \
       r"derelict|structural|subsidence|damp|updat|scheme of works|attention)"
print("\nreal phrasing around condition cues:")
seen = collections.Counter()
for r in rows:
    for m in re.finditer(CUES, r["description"] or "", re.I):
        s = max(0, m.start() - 45)
        phrase = re.sub(r"\s+", " ", r["description"][s:m.end() + 25]).strip()
        seen[phrase.lower()] += 1
for p, c in seen.most_common(45):
    print(f"  {c:2}  ...{p}...")
