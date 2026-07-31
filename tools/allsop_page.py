"""Work out how to page through Allsop's /api/search results."""
import requests

BASE = "https://www.allsop.co.uk"
AID = "d8f13938-f220-11f0-a09f-0242ac110002"
S = requests.Session()
S.headers.update({"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
                  "Accept": "application/json, text/plain, */*"})


def ids(params):
    d = S.get(f"{BASE}/api/search", params={"auction_id": AID, **params}, timeout=60)
    d = d.json().get("data", {})
    res = d.get("results", [])
    return d.get("total"), [x.get("allsop_lotnumber") for x in res]


base_total, base_lots = ids({})
print(f"baseline: total={base_total} n={len(base_lots)} lots={base_lots[:6]}")

for params in ({"page": 2}, {"page": "2"}, {"from": 20}, {"offset": 20},
               {"per_page": 100}, {"size": 100}, {"limit": 100},
               {"page": 1, "per_page": 100}, {"results_per_page": 100}):
    try:
        total, lots = ids(params)
    except Exception as e:
        print(f"  {params}: ERR {e}")
        continue
    same = lots[:6] == base_lots[:6]
    print(f"  {str(params):32} total={total} n={len(lots):3} "
          f"{'(same page)' if same else 'DIFFERENT -> ' + str(lots[:6])}")
