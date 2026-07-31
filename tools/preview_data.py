"""Build a compact JSON summary of the scraped corpus for the preview page.

Usage: python preview_data.py ../data/sdl_all.jsonl ../data/bw_all.jsonl
"""
import collections, json, statistics, sys

sys.path.insert(0, "../src")
from enrich import classify_condition

from geo import load_cache

lots = []
for path in sys.argv[1:]:
    lots += [json.loads(l) for l in open(path, encoding="utf-8")]

geo = load_cache()
for l in lots:
    g = geo.get(l.get("postcode") or "")
    l["region"] = g["region"] if g else None
    l["district"] = g["admin_district"] if g else None

# Descriptions were fetched separately for a sample of SDL lots.
try:
    desc = {r["source_lot_id"]: r["description"]
            for r in json.load(open("../data/sampled.json", encoding="utf-8"))}
except FileNotFoundError:
    desc = {}

for l in lots:
    d = l.get("description") or desc.get(l["source_lot_id"], "")
    l["condition"] = classify_condition(d)[0] if d else None
    g, h = l.get("guide_price"), l.get("hammer_price")
    l["uplift_pct"] = round((h - g) / g * 100) if (h and g and g >= 1000) else None

sold = [l for l in lots if l["hammer_price"]]
up = [l["uplift_pct"] for l in lots if l["uplift_pct"] is not None]
events = {(l["source"], l["auction_date"]) for l in lots if l["auction_date"]}

# Cross-source signal: the same property offered at more than one auction house.
seen = collections.defaultdict(set)
for l in lots:
    if l["property_key"]:
        seen[l["property_key"]].add(l["source"])
reoffers = collections.Counter(l["property_key"] for l in lots if l["property_key"])

summary = {
    "total": len(lots),
    "sources": dict(collections.Counter(l["source"] for l in lots).most_common()),
    "events": len(events),
    "status": dict(collections.Counter(l["status"] for l in lots).most_common()),
    "sold_n": len(sold),
    "hammer_median": int(statistics.median(l["hammer_price"] for l in sold)),
    "total_raised": sum(l["hammer_price"] for l in sold),
    "uplift_median": int(statistics.median(up)) if up else None,
    "uplift_n": len(up),
    "over_guide": sum(1 for u in up if u > 0),
    "repeat_properties": sum(1 for n in reoffers.values() if n > 1),
    "cross_source_properties": sum(1 for v in seen.values() if len(v) > 1),
    "date_min": min(l["auction_date"] for l in lots if l["auction_date"]),
    "date_max": max(l["auction_date"] for l in lots if l["auction_date"]),
    "geo_resolved": sum(1 for l in lots if l["region"]),
    "districts": len({l["district"] for l in lots if l["district"]}),
    # Price-disclosure rate per house — the spread between them is the point.
    "priced_by_source": {
        src: round(100 * sum(1 for l in lots if l["source"] == src and l["hammer_price"])
                   / sum(1 for l in lots if l["source"] == src))
        for src in {l["source"] for l in lots}},
}

# Regional breakdown: the reason a single national HPI index was wrong.
by_region = collections.defaultdict(list)
for l in sold:
    if l["region"]:
        by_region[l["region"]].append(l["hammer_price"])
summary["regions"] = sorted(
    ({"region": k, "n": len(v), "median": int(statistics.median(v)), "total": sum(v)}
     for k, v in by_region.items() if len(v) >= 15),
    key=lambda r: -r["n"])
print(json.dumps(summary, indent=1))

keep = ("source", "address_raw", "postcode", "property_type", "bedrooms", "guide_price",
        "hammer_price", "uplift_pct", "status", "condition", "lot_url", "auction_date",
        "region", "district")


def slim(rows):
    return [{k: r.get(k) for k in keep} for r in rows]


# Biggest sales carry the story; cap so the page stays light.
top = sorted(sold, key=lambda l: -l["hammer_price"])[:150]
repeat = sorted((l for l in lots if reoffers[l["property_key"]] > 2 and l["property_key"]),
                key=lambda l: (l["property_key"], l["auction_date"] or ""))[:60]

out = {"summary": summary, "sold": slim(top), "repeat": slim(repeat)}
json.dump(out, open("../data/preview.json", "w", encoding="utf-8"), indent=1)
print(f"\nwrote {len(out['sold'])} sold + {len(out['repeat'])} repeat rows")
