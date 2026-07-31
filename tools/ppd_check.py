"""Is the Land Registry Price Paid data reachable, and how big?"""
import requests

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
ROOT = "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"

URLS = [
    f"{ROOT}/pp-2026.csv",
    f"{ROOT}/pp-2025.csv",
    f"{ROOT}/pp-2024.csv",
    f"{ROOT}/pp-monthly-update-new-version.csv",
    f"{ROOT}/pp-complete.csv",
]
for u in URLS:
    try:
        r = requests.head(u, headers=HEADERS, timeout=30, allow_redirects=True)
        size = r.headers.get("content-length")
        mb = f"{int(size)/1e6:,.0f} MB" if size else "?"
        print(f"  {r.status_code}  {mb:>10}  {u.rsplit('/', 1)[1]}")
    except requests.RequestException as e:
        print(f"  ERR {type(e).__name__}  {u.rsplit('/', 1)[1]}")

# Peek at the first rows to confirm column order matches enrich.load_ppd.
r = requests.get(f"{ROOT}/pp-2025.csv", headers=HEADERS, timeout=60, stream=True)
print("\nfirst 2 rows of pp-2025.csv:")
for i, line in enumerate(r.iter_lines(decode_unicode=True)):
    print("  ", line[:200])
    if i >= 1:
        break
r.close()
