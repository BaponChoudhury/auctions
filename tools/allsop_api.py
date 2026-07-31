"""Try to find the JSON endpoint that serves Allsop lots for an auction."""
import json, requests

BASE = "https://www.allsop.co.uk"
AID = "eb91d024-f848-11f0-a7b9-0242ac110002"
S = requests.Session()
S.headers.update({
    "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": f"{BASE}/property-search?auction_id={AID}&view=table",
})

print("=== /api/getenvvars ===")
r = S.get(f"{BASE}/api/getenvvars", timeout=30)
print(r.status_code, r.headers.get("content-type"), r.text[:600])

CANDIDATES = [
    f"/api/search?auction_id={AID}",
    f"/api/lot/?auction_id={AID}",
    f"/api/lots?auction_id={AID}",
    f"/api/property-search?auction_id={AID}",
    f"/property-search?auction_id={AID}&view=table&format=json",
    f"/api/search/lots?auction_id={AID}",
    f"/api/auction/{AID}/lots",
    f"/api/auctions/{AID}",
]
print("\n=== candidates ===")
for path in CANDIDATES:
    try:
        r = S.get(BASE + path, timeout=30)
    except requests.RequestException as e:
        print(f"  {path[:56]:58} ERR {type(e).__name__}")
        continue
    ct = (r.headers.get("content-type") or "")[:30]
    note = ""
    if "json" in ct:
        try:
            j = r.json()
            note = f"keys={list(j)[:6]}" if isinstance(j, dict) else f"list[{len(j)}]"
        except ValueError:
            note = "unparseable"
    print(f"  {path[:56]:58} {r.status_code} {ct:30} {len(r.text):7} {note}")
