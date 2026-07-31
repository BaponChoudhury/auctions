"""Is Allsop's low match rate explained by PPD being residential-only?"""
import collections, json

rows = [json.loads(l) for l in open("../data/matched.jsonl", encoding="utf-8") if l.strip()]
SOLD = ("sold", "sold_prior", "sold_after")
sold = [r for r in rows if r["status"] in SOLD and r.get("postcode")
        and r.get("auction_date")]

print("match rate for SOLD lots, by source and property type")
print("(PPD registers residential sales only; 'O' is land/commercial)\n")
print(f"{'source':11} {'type':6} {'lots':>7} {'matched':>8} {'rate':>6}")
grp = collections.defaultdict(list)
for r in sold:
    grp[(r["source"], r["property_type"] or "?")].append(r)
for (src, t), sub in sorted(grp.items(), key=lambda x: (x[0][0], x[0][1])):
    if len(sub) < 25:
        continue
    m = sum(1 for r in sub if r["recovered_price"] is not None)
    print(f"{src:11} {t:6} {len(sub):7,} {m:8,} {100*m//len(sub):5}%")

print("\nresidential (D/S/T/F) vs other, per source:")
for src in sorted({r["source"] for r in sold}):
    res = [r for r in sold if r["source"] == src and r["property_type"] in ("D", "S", "T", "F")]
    oth = [r for r in sold if r["source"] == src and r["property_type"] not in ("D", "S", "T", "F")]
    for label, sub in (("residential", res), ("other/commercial", oth)):
        if not sub:
            continue
        m = sum(1 for r in sub if r["recovered_price"] is not None)
        print(f"  {src:11} {label:18} {m:5,}/{len(sub):5,}  {100*m//len(sub):3}%")
