"""How far does PPD actually reach, and does that explain the low match rates?"""
import collections, csv, glob, json

latest = ""
counts = collections.Counter()
for path in glob.glob("../data/ppd/*.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) > 3:
                d = row[2][:10]
                latest = max(latest, d)
                counts[d[:7]] += 1
print(f"latest transfer_date anywhere in the PPD extracts: {latest}")
print("\nrecent months (registrations tail off as completions are still being lodged):")
for m in sorted(counts)[-8:]:
    print(f"  {m}  {counts[m]:>8,}")

rows = [json.loads(l) for l in open("../data/matched.jsonl", encoding="utf-8") if l.strip()]
SOLD = ("sold", "sold_prior", "sold_after")
print("\nmatch rate for SOLD lots by auction month (all sources):")
grp = collections.defaultdict(list)
for r in rows:
    if r["status"] in SOLD and r.get("auction_date"):
        grp[r["auction_date"][:7]].append(r)
for m in sorted(grp)[-14:]:
    sub = grp[m]
    hit = sum(1 for r in sub if r["recovered_price"] is not None)
    srcs = ",".join(sorted({r["source"][:4] for r in sub}))
    print(f"  {m}  {hit:5,}/{len(sub):5,}  {100*hit//len(sub):3}%   {srcs}")
