"""Find the request shape that returns AUCTION LOTS (with results) for an auction."""
import json, sys, requests

BASE = "https://www.allsop.co.uk"
AID = sys.argv[1] if len(sys.argv) > 1 else "eb91d024-f848-11f0-a7b9-0242ac110002"
S = requests.Session()
S.headers.update({
    "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE}/property-search?auction_id={AID}&view=table",
})

TRIES = [
    ("/api/search", {"auction_id": AID}),
    ("/api/search", {"auction_id": AID, "view": "table"}),
    ("/api/search", {"auction_id": AID, "type": "lot"}),
    ("/api/search", {"auction_id": AID, "per_page": "200", "page": "1"}),
    ("/api/property-search", {"auction_id": AID, "type": "lot"}),
]

for path, params in TRIES:
    r = S.get(BASE + path, params=params, timeout=60)
    try:
        j = r.json()
    except ValueError:
        print(f"{path} {params}: non-JSON"); continue
    d = j.get("data", {})
    res = d.get("results", []) if isinstance(d, dict) else []
    total = d.get("total") if isinstance(d, dict) else None
    types = {x.get("type") for x in res}
    haslot = sum(1 for x in res if x.get("allsop_lotid") or x.get("lot_number"))
    print(f"{path} {params}")
    print(f"   results={len(res)} total={total} types={types} with_lot_id={haslot}")
    if haslot:
        json.dump(res[:3], open("allsop_sample.json", "w", encoding="utf-8"), indent=1)
        lot = next(x for x in res if x.get("allsop_lotid") or x.get("lot_number"))
        print("\n--- an auction lot ---")
        for k in sorted(lot):
            v = lot[k]
            s = v if isinstance(v, str) else json.dumps(v)
            print(f"   {k:34} {s[:80]}")
        break
