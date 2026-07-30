import json
d = json.load(open("preview.json", encoding="utf-8"))
for r in d["sold"][:6]:
    print(f"{r['uplift_pct']:>6}%  guide={r['guide_price']:>9}  hammer={r['hammer_price']:>9}  "
          f"{r['address_raw'][:50]}")
    print(f"         raw={r['result_raw']!r}  url={r['lot_url']}")
