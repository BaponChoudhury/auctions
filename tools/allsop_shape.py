"""Inspect the Allsop property-search JSON so selectors are written from fact."""
import json, requests

BASE = "https://www.allsop.co.uk"
AID = "eb91d024-f848-11f0-a7b9-0242ac110002"
S = requests.Session()
S.headers.update({
    "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE}/property-search?auction_id={AID}&view=table",
})

j = S.get(f"{BASE}/api/property-search", params={"auction_id": AID}, timeout=60).json()
print("top keys:", list(j))
data = j["data"]
print("data type:", type(data).__name__,
      "keys:" if isinstance(data, dict) else "len:",
      list(data)[:12] if isinstance(data, dict) else len(data))

lots = data if isinstance(data, list) else (
    data.get("lots") or data.get("results") or data.get("hits") or [])
print("\nlots:", len(lots))
if lots:
    lot = lots[0]
    print("\n--- one lot's fields ---")
    for k in sorted(lot):
        v = lot[k]
        s = json.dumps(v)[:88] if not isinstance(v, str) else v[:88]
        print(f"  {k:34} {s}")
    json.dump(lots[:3], open("allsop_sample.json", "w", encoding="utf-8"), indent=1)

    # Which fields carry price / status / address?
    print("\n--- fields present across all lots ---")
    keys = {}
    for l in lots:
        for k, v in l.items():
            if v not in (None, "", [], {}):
                keys[k] = keys.get(k, 0) + 1
    for k, n in sorted(keys.items(), key=lambda x: -x[1]):
        if any(t in k.lower() for t in
               ("price", "sold", "status", "address", "postcode", "result", "lot", "type", "bed")):
            print(f"  {k:34} {n}/{len(lots)}")
