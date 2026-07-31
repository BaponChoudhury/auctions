"""Pick the match window from evidence: which window maximises agreement with
the hammer prices we already know, rather than just maximising match count?"""
import json, sys
sys.path.insert(0, "../src")
from ppd_match import candidates, load_ppd, PPD_DIR

lots = []
for p in ("../data/sdl_all.jsonl", "../data/bw_full.jsonl", "../data/allsop_all.jsonl"):
    lots += [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

postcodes = {(l.get("postcode") or "").upper() for l in lots if l.get("postcode")}
index = load_ppd(postcodes, sorted(str(x) for x in PPD_DIR.glob("*.csv")))

known = [l for l in lots if l.get("hammer_price")]
print(f"\nvalidating against {len(known):,} lots with a published hammer price\n")
print(f"{'before':>7} {'after':>6} {'matched':>8} {'exact':>7} {'exact%':>7} "
      f"{'ambiguous':>10}")

for before, after in [(30, 120), (14, 120), (7, 120), (0, 120),
                      (0, 90), (0, 60), (0, 45), (-1, 120)]:
    matched = exact = ambig = 0
    for lot in known:
        hits = candidates(lot, index, before, after)
        if not hits:
            continue
        matched += 1
        ambig += len(hits) > 1
        if hits[0]["price"] == lot["hammer_price"]:
            exact += 1
    pct = 100 * exact // matched if matched else 0
    print(f"{before:7} {after:6} {matched:8,} {exact:7,} {pct:6}% {ambig:10,}")
