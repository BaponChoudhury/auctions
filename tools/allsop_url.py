"""Confirm the public URL pattern for an Allsop lot (don't guess it into the data)."""
import requests

BASE = "https://www.allsop.co.uk"
S = requests.Session()
S.headers.update({"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
                  "Accept": "text/html,application/json"})
AID = "d8f13938-f220-11f0-a09f-0242ac110002"

d = S.get(f"{BASE}/api/search", params={"auction_id": AID, "size": 5}, timeout=60).json()["data"]
lot = next(x for x in d["results"] if x.get("allsop_lotid"))
lid, ref, num = lot["allsop_lotid"], lot.get("reference"), lot.get("lot_number")
print("lotid:", lid, "| reference:", ref, "| lot_number:", num)

for path in (f"/lot/{lid}", f"/lots/{lid}", f"/property-search/lot/{lid}",
             f"/lot/{ref}", f"/auction-lot/{lid}"):
    try:
        r = S.get(BASE + path, timeout=30, allow_redirects=True)
        title = ""
        if "html" in (r.headers.get("content-type") or ""):
            import re
            m = re.search(r"<title>(.*?)</title>", r.text, re.S)
            title = (m.group(1).strip()[:70] if m else "")
        print(f"  {path[:52]:54} {r.status_code} {len(r.text):7} {title}")
    except requests.RequestException as e:
        print(f"  {path[:52]:54} ERR {type(e).__name__}")
