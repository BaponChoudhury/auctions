"""Download Land Registry Price Paid yearly extracts (OGL)."""
import pathlib, sys
import requests

ROOT = ("http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1"
        ".amazonaws.com")
HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
OUT = pathlib.Path(__file__).parent.parent / "data" / "ppd"
OUT.mkdir(parents=True, exist_ok=True)

for year in sys.argv[1:] or ["2024", "2025", "2026"]:
    dest = OUT / f"pp-{year}.csv"
    if dest.exists():
        print(f"pp-{year}.csv already present ({dest.stat().st_size/1e6:,.0f} MB)")
        continue
    print(f"downloading pp-{year}.csv ...")
    with requests.get(f"{ROOT}/pp-{year}.csv", headers=HEADERS,
                      timeout=120, stream=True) as r:
        r.raise_for_status()
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if done % (25 << 20) < (1 << 20):
                    print(f"  {done/1e6:,.0f} MB")
    print(f"  -> {dest} ({dest.stat().st_size/1e6:,.0f} MB)")
