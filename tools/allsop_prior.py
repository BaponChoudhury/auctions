"""Does Allsop publish sale_price for Sold Prior / Sold After lots?"""
import collections, requests

BASE = "https://www.allsop.co.uk"
AID = "d8f13938-f220-11f0-a09f-0242ac110002"
S = requests.Session()
S.headers.update({"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
                  "Accept": "application/json, text/plain, */*"})
res = S.get(f"{BASE}/api/search", params={"auction_id": AID, "size": 500},
            timeout=60).json()["data"]["results"]

tally = collections.defaultdict(lambda: [0, 0])
for lot in res:
    if not lot.get("allsop_lotid"):
        continue
    st = (lot.get("allsop_lotstatus") or "?").strip()
    tally[st][0] += 1
    if lot.get("sale_price") not in (None, "", 0, "0.00"):
        tally[st][1] += 1

print(f"{'status':16} {'lots':>5} {'with sale_price':>16}")
for st, (n, priced) in sorted(tally.items()):
    print(f"  {st:14} {n:5} {priced:16}")

print("\nexamples where status is Sold Prior/After:")
for lot in res:
    st = (lot.get("allsop_lotstatus") or "")
    if "Prior" in st or "After" in st:
        print(f"  {st:12} sale_price={lot.get('sale_price')!r:14} "
              f"guide={lot.get('guide_price_text')!r:22} {lot.get('allsop_address','')[:40]}")
