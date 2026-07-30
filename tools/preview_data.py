"""Build a compact JSON summary of a scraped event for the preview page."""
import json, statistics, sys, collections
sys.path.insert(0, "../src")
from enrich import classify_condition

lots = [json.loads(l) for l in open("../data/lots_1267.jsonl", encoding="utf-8")]
desc = {r["source_lot_id"]: r["description"]
        for r in json.load(open("../data/sampled.json", encoding="utf-8"))}

for l in lots:
    d = desc.get(l["source_lot_id"], "")
    l["description"] = d
    l["condition"] = classify_condition(d)[0] if d else None
    if l["hammer_price"] and l["guide_price"]:
        l["uplift_pct"] = round((l["hammer_price"] - l["guide_price"]) / l["guide_price"] * 100)
    else:
        l["uplift_pct"] = None

sold = [l for l in lots if l["hammer_price"]]
# Nominal guides (a land parcel guided at £1 that sold for £100) are real, but a
# 9,900% uplift makes any percentage aggregate meaningless. Keep the lot, drop it
# from the ratio stats.
MIN_GUIDE = 1000
nominal = [l for l in sold if l["guide_price"] and l["guide_price"] < MIN_GUIDE]
up = [l["uplift_pct"] for l in sold
      if l["uplift_pct"] is not None and l["guide_price"] >= MIN_GUIDE]

summary = {
    "auction_date": lots[0]["auction_date"],
    "total": len(lots),
    "status": dict(collections.Counter(l["status"] for l in lots).most_common()),
    "types": dict(collections.Counter(l["property_type"] for l in lots).most_common()),
    "sold_n": len(sold),
    "guide_median": int(statistics.median(l["guide_price"] for l in sold)),
    "hammer_median": int(statistics.median(l["hammer_price"] for l in sold)),
    "uplift_median": int(statistics.median(up)),
    "uplift_max": max(up),
    "over_guide": sum(1 for u in up if u > 0),
    "under_guide": sum(1 for u in up if u < 0),
    "total_raised": sum(l["hammer_price"] for l in sold),
    "nominal_excluded": len(nominal),
}
print(json.dumps(summary, indent=1))

keep = ("address_raw", "postcode", "postcode_sector", "property_type", "bedrooms",
        "guide_price", "hammer_price", "uplift_pct", "status", "result_raw",
        "property_key", "condition", "lot_url")
rows = sorted(sold, key=lambda l: -(l["uplift_pct"] or -999))
out = {"summary": summary, "sold": [{k: l[k] for k in keep} for l in rows],
       "unsold": [{k: l[k] for k in keep} for l in lots if l["status"] == "unsold"][:12]}
json.dump(out, open("../data/preview.json", "w", encoding="utf-8"), indent=1)
print(f"\nwrote {len(out['sold'])} sold + {len(out['unsold'])} unsold rows")
