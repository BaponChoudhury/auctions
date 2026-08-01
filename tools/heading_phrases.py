"""What condition phrasing do auction HEADINGS actually use?
Headings are terse and upper-case; the prose ruleset was built for sentences."""
import collections, json, re

rows = [json.loads(l) for l in open("../data/emson_all.jsonl", encoding="utf-8") if l.strip()]
CUE = (r"(improvement|improve|modernisation|modernis\w*|refurbishment|refurb\w*|"
       r"renovation|renovat\w*|repair\w*|updating|updat\w*|potential|dilapidated|"
       r"derelict|require\w*|needing|in need of|scope|development)")

phrases = collections.Counter()
for r in rows:
    d = r["description"] or ""
    for m in re.finditer(CUE, d, re.I):
        s = max(0, m.start() - 34)
        frag = re.sub(r"\s+", " ", d[s:m.end() + 20]).strip().lower()
        phrases[frag] += 1
for p, n in phrases.most_common(30):
    print(f"  {n:4}  ...{p}...")

print("\n--- how does 'potential' get used? (development vs condition) ---")
pot = [r["description"] for r in rows if re.search(r"potential", r["description"] or "", re.I)]
for d in pot[:10]:
    print(f"  {d[:80]}")
