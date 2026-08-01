"""Verify the EPC credentials work and see what a lookup actually returns.
Loads credentials from the user's existing .env; never prints the key."""
import os, sys, time
import requests
from dotenv import load_dotenv

load_dotenv(r"C:\Users\bapon\autoPosting\.env")
sys.path.insert(0, "../src")
from enrich import epc_lookup, EPC_URL

email, key = os.environ.get("EPC_EMAIL"), os.environ.get("EPC_KEY")
print("EPC_EMAIL set:", bool(email), "| EPC_KEY set:", bool(key),
      f"({len(key)} chars)" if key else "")

import base64
tok = base64.b64encode(f"{email}:{key}".encode()).decode()
r = requests.get(EPC_URL, params={"postcode": "DE14 2EG", "size": 5},
                 headers={"Authorization": f"Basic {tok}", "Accept": "application/json"},
                 timeout=30)
print("\nraw API check:", r.status_code, r.headers.get("content-type"))
if r.status_code != 200:
    print("body:", r.text[:300]); sys.exit(1)
rows = r.json().get("rows", [])
print("rows returned:", len(rows))
if rows:
    print("\nfields available on a certificate:")
    for k in sorted(rows[0]):
        print(f"  {k:34} {str(rows[0][k])[:52]}")

print("\n--- epc_lookup() against real corpus addresses ---")
CASES = [
    ("DE14 2EG", "9 Byrkley Street, Burton-On-Trent DE14 2EG"),
    ("SK4 1PS", "7 Reuben Street, Stockport, Greater Manchester SK4 1PS"),
    ("B20 2JH", "The Cottage, 59 College Road, Handsworth, Birmingham, B20 2JH"),
]
s = requests.Session()
for pc, addr in CASES:
    res = epc_lookup(pc, addr, s)
    print(f"  {pc:9} -> {res}")
    time.sleep(1)
