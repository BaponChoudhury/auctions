"""Get past Allsop auction ids, then find the sold-price/status fields."""
import json, re, requests

BASE = "https://www.allsop.co.uk"
S = requests.Session()
S.headers.update({
    "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
    "Accept": "application/json, text/plain, */*",
})

html = S.get(f"{BASE}/auctions/past-auction-results/", timeout=30).text
ids = []
for m in re.finditer(r"/property-search\?auction_id=([0-9a-f\-]+)", html):
    if m.group(1) not in ids:
        ids.append(m.group(1))
print(f"past auction ids on the index: {len(ids)}")

# Use one a few months back so results are published.
for aid in ids[2:6]:
    r = S.get(f"{BASE}/api/search", params={"auction_id": aid}, timeout=60)
    d = r.json().get("data", {})
    res, total = d.get("results", []), d.get("total")
    lots = [x for x in res if x.get("allsop_lotid")]
    statuses = {x.get("allsop_lotstatus") for x in lots}
    print(f"\n{aid}  total={total} results={len(res)} lots={len(lots)} statuses={statuses}")
    if not lots:
        continue
    # Which fields look like a sale result?
    sold_fields = {}
    for x in lots:
        for k, v in x.items():
            if v in (None, "", [], {}):
                continue
            if re.search(r"sold|result|hammer|sale_price|realis", k, re.I):
                sold_fields.setdefault(k, set()).add(str(v)[:40])
    if sold_fields:
        print("  result-ish fields:")
        for k, vals in sold_fields.items():
            print(f"    {k:34} {list(vals)[:4]}")
        json.dump(lots[:3], open("allsop_sold_sample.json", "w", encoding="utf-8"), indent=1)
        print("\n  full key list of one lot:")
        print("   ", ", ".join(sorted(lots[0])))
        break
