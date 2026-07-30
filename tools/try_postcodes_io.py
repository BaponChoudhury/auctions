"""Can postcodes.io give us local authority + ONS codes for HPI matching?"""
import json, requests

r = requests.post("https://api.postcodes.io/postcodes",
                  json={"postcodes": ["DE14 2EG", "SK4 1PS", "B20 2JH", "SW2 3LR",
                                      "CW1 2NE", "NOTAPOSTCODE"]},
                  timeout=30)
print("status:", r.status_code)
payload = r.json()
print("top-level status:", payload.get("status"))
for item in payload["result"]:
    q, res = item["query"], item["result"]
    if not res:
        print(f"\n{q}: NO MATCH")
        continue
    print(f"\n{q}")
    for k in ("admin_district", "admin_county", "admin_ward", "region", "country",
              "parliamentary_constituency", "lsoa", "longitude", "latitude"):
        print(f"   {k:28} {res.get(k)}")
    print(f"   codes.admin_district         {res['codes'].get('admin_district')}")
    print(f"   codes.admin_county           {res['codes'].get('admin_county')}")
