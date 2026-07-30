"""Inject the scraped preview data into the template and emit the artifact HTML."""
import json, pathlib, sys

here = pathlib.Path(__file__).parent
data = json.loads((here.parent / "data" / "preview.json").read_text(encoding="utf-8"))
tpl = (here / "preview_template.html").read_text(encoding="utf-8")

# </script> inside the JSON payload would close the host <script> tag early.
payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
out = pathlib.Path(sys.argv[1])
# newline="" keeps LF endings; the Windows default rewrites them to CRLF.
with open(out, "w", encoding="utf-8", newline="") as f:
    f.write(tpl.replace("__DATA__", payload))
rows = ", ".join(f"{len(v)} {k}" for k, v in data.items() if isinstance(v, list))
print(f"wrote {out} ({out.stat().st_size} bytes, {rows})")
