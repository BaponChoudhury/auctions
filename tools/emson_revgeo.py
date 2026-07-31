"""Can postcodes.io turn Clive Emson's lat/lon into the right postcode?
Ground truth: lot 1 of auction 259 is 90 Canterbury Road, Margate, CT9 5DF."""
import requests
from bs4 import BeautifulSoup

soup = BeautifulSoup(open("emson_probe.html", encoding="utf-8").read(), "html.parser")
uniq = {}
for l in soup.select(".lot"):
    k = l.get("data-lot")
    if k and k not in uniq:
        uniq[k] = l

pts = []
for lot in list(uniq.values())[:20]:
    lonlat = (lot.get("data-lonlat") or "").split(",")
    if len(lonlat) == 2:
        # data-lonlat is actually "lat,lon" judging by 51.38,1.36 for Margate.
        pts.append({"latitude": float(lonlat[0]), "longitude": float(lonlat[1]),
                    "limit": 1, "radius": 500})

r = requests.post("https://api.postcodes.io/postcodes",
                  json={"geolocations": pts}, timeout=45)
print("status:", r.status_code)
res = r.json()["result"]
for lot, item in zip(list(uniq.values())[:20], res):
    hits = item.get("result") or []
    pc = hits[0]["postcode"] if hits else None
    dist = f"{hits[0]['distance']:.0f}m" if hits else "-"
    ward = hits[0]["admin_district"] if hits else "-"
    print(f"  lot {lot.get('data-lot'):>3}  {str(lot.get('data-loc'))[:26]:28} "
          f"-> {str(pc):9} {dist:>7}  {ward}")
