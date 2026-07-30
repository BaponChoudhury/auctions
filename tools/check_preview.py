"""Static checks on the built artifact: payload validity and template completeness."""
import json, pathlib, re, sys

html = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
assert "__DATA__" not in html, "template placeholder was not replaced"

m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', html, re.S)
assert m, "payload script block not found"
raw = m.group(1)
assert "</script>" not in raw, "unescaped </script> inside payload"
data = json.loads(raw.replace("<\\/", "</"))

# Nothing may close the host <script> early.
assert re.search(r"</script\b", raw) is None

print("payload parses OK")
print("  sold rows   :", len(data["sold"]))
print("  repeat rows :", len(data["repeat"]))
print("  summary keys:", ", ".join(data["summary"]))

# Keys the renderer reads must exist on every row.
needed = {"source", "address_raw", "postcode", "property_type", "guide_price",
          "hammer_price", "uplift_pct", "condition", "lot_url", "auction_date"}
for bucket in ("sold", "repeat"):
    for i, r in enumerate(data[bucket]):
        missing = needed - set(r)
        assert not missing, f"{bucket}[{i}] missing {missing}"
print("all rows carry every key the renderer reads")

# Every status the chart draws must exist in the summary.
for k in ("sold_prior", "sold", "unsold", "withdrawn", "postponed", "sold_after", "listed"):
    assert k in data["summary"]["status"], f"status {k} missing"
print("status chart keys present")

s = data["summary"]
assert s["total"] == sum(s["sources"].values()), (s["total"], s["sources"])
assert s["total"] == sum(s["status"].values()), "status counts do not sum to total"
assert len(s["sources"]) >= 2, "preview claims two sources but data has fewer"
assert {r["source"] for r in data["sold"]} <= set(s["sources"])
# The table is a top-N sample, so it must not claim to be the whole set.
assert len(data["sold"]) <= s["sold_n"]
print(f"consistent: {s['total']:,} lots, {len(s['sources'])} sources, "
      f"{s['sold_n']:,} sold, GBP {s['total_raised']:,}")

# The prose hard-codes these; if the data moves, the copy is wrong.
assert f"{s['total']:,}" in html, "headline total not present in page copy"
assert str(s["events"]) in html, "event count not present in page copy"
print("page copy matches the data it describes")

for tag in ("<title>", "</style>", "</script>"):
    assert tag in html, tag
print("html structure OK ->", len(html), "bytes")
