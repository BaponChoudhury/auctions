"""Does the existing 64-char EPC_KEY work against the NEW API?
Some service migrations carry keys across. Cheaper to test than to assume.
Never prints the key itself."""
import base64, os, pathlib
import requests
from dotenv import load_dotenv

for env in (pathlib.Path(__file__).parent.parent / ".env",
            pathlib.Path(r"C:\Users\bapon\autoPosting\.env")):
    if env.exists():
        load_dotenv(env)

API = "https://api.get-energy-performance-data.communities.gov.uk"
email = os.environ.get("EPC_EMAIL", "")
key = os.environ.get("EPC_KEY", "")
print(f"EPC_EMAIL present: {bool(email)} | EPC_KEY present: {bool(key)} "
      f"({len(key)} chars)")

basic = base64.b64encode(f"{email}:{key}".encode()).decode()
ATTEMPTS = [
    ("bearer = EPC_KEY",            {"Authorization": f"Bearer {key}"}),
    ("bearer = base64(email:key)",  {"Authorization": f"Bearer {basic}"}),
    ("basic  = email:key (old style)", {"Authorization": f"Basic {basic}"}),
    ("no auth at all",              {}),
]
for label, auth in ATTEMPTS:
    try:
        r = requests.get(f"{API}/api/domestic/search",
                         params={"postcode": "DE14 2EG"},
                         headers={"Accept": "application/json",
                                  "User-Agent": "AuctionResearchBot/0.1 "
                                                "(contact: mailahb2017@gmail.com)",
                                  **auth},
                         timeout=45)
        ct = (r.headers.get("content-type") or "")[:24]
        note = ""
        if r.status_code == 200 and "json" in ct:
            try:
                data = r.json().get("data") or []
                note = f"-> {len(data)} certificates"
            except ValueError:
                note = "-> 200 but unparseable"
        else:
            note = r.text[:110].replace("\n", " ")
        print(f"  {label:32} {r.status_code} {ct:24} {note}")
    except requests.RequestException as e:
        print(f"  {label:32} ERR {type(e).__name__}")
