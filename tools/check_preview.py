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
print("  unsold rows :", len(data["unsold"]))
print("  summary keys:", ", ".join(data["summary"]))

# Keys the renderer reads must exist on every row.
needed = {"address_raw", "postcode", "property_type", "guide_price",
          "hammer_price", "uplift_pct", "condition", "lot_url"}
for bucket in ("sold", "unsold"):
    for i, r in enumerate(data[bucket]):
        missing = needed - set(r)
        assert not missing, f"{bucket}[{i}] missing {missing}"
print("all rows carry every key the renderer reads")

# Every status the chart draws must exist in the summary.
for k in ("sold_prior", "sold", "unsold", "withdrawn", "postponed", "sold_after"):
    assert k in data["summary"]["status"], f"status {k} missing"
print("status chart keys present")

# Headline figures quoted in the prose must match the data.
s = data["summary"]
assert s["total"] == 224 and s["sold_n"] == 55, (s["total"], s["sold_n"])
assert len(data["sold"]) == s["sold_n"], "table row count disagrees with headline"
raised = sum(r["hammer_price"] for r in data["sold"])
assert raised == s["total_raised"], (raised, s["total_raised"])
assert abs(raised / 1e6 - 8.69) < 0.01, raised
print(f"headline figures agree with rows: 224 lots, 55 sold, GBP {raised:,}")

for tag in ("<title>", "</style>", "</script>"):
    assert tag in html, tag
print("html structure OK ->", len(html), "bytes")
