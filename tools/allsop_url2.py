import re, requests

BASE = "https://www.allsop.co.uk"
S = requests.Session()
S.headers.update({"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
                  "Accept": "text/html,application/json"})
AID = "d8f13938-f220-11f0-a09f-0242ac110002"
d = S.get(f"{BASE}/api/search", params={"auction_id": AID, "size": 5}, timeout=60).json()["data"]
lot = next(x for x in d["results"] if x.get("allsop_lotid"))
print("address:", lot["allsop_address"])
for key in ("version_id", "allsop_lotid", "allsop_property_version_id"):
    v = lot.get(key)
    if not v:
        continue
    url = f"{BASE}/lot-overview?versionId={v}"
    r = S.get(url, timeout=30)
    m = re.search(r"<title>(.*?)</title>", r.text, re.S)
    print(f"  {key:28} {r.status_code} {len(r.text):7} {m.group(1).strip()[:70] if m else ''}")
