"""What do Clive Emson's lot data-attributes actually carry, per status?"""
import collections, re
from bs4 import BeautifulSoup

soup = BeautifulSoup(open("emson_probe.html", encoding="utf-8").read(), "html.parser")
lots = soup.select(".lot")
print("elements with class 'lot':", len(lots))
uniq = {}
for l in lots:
    key = (l.get("data-auc"), l.get("data-lot"))
    if key[1] and key not in uniq:
        uniq[key] = l
print("unique (auction, lot) pairs:", len(uniq))

print("\nattributes present:")
attrs = collections.Counter()
for l in uniq.values():
    for k in l.attrs:
        attrs[k] += 1
for k, n in attrs.most_common():
    print(f"  {k:16} {n}")

print("\nstatus vocabulary (data-ceastatus) and whether a price comes with it:")
tally = collections.defaultdict(lambda: [0, 0])
for l in uniq.values():
    st = (l.get("data-ceastatus") or "?").strip()
    tally[st][0] += 1
    if (l.get("data-price") or "").strip():
        tally[st][1] += 1
for st, (n, priced) in sorted(tally.items(), key=lambda x: -x[1][0]):
    print(f"  {st:18} {n:4} lots, {priced:4} with data-price")

print("\nsample rows:")
for l in list(uniq.values())[:6]:
    print(f"  lot {l.get('data-lot'):>4} {str(l.get('data-ceastatus')):10} "
          f"£{str(l.get('data-price')):>10}  {str(l.get('data-loc'))[:28]:30} "
          f"{l.get('data-lonlat')}")
    print(f"        {str(l.get('data-cathead'))[:88]}")

print("\ndoes any lot carry a postcode or street address anywhere?")
blob = open("emson_probe.html", encoding="utf-8").read()
pcs = re.findall(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", blob)
print(f"  postcode-shaped strings in the page: {len(pcs)} {pcs[:5]}")
