"""What is the EPC API actually returning? Never prints the key."""
import base64, os, re
import requests
from dotenv import load_dotenv

load_dotenv(r"C:\Users\bapon\autoPosting\.env")
email, key = os.environ["EPC_EMAIL"], os.environ["EPC_KEY"]
tok = base64.b64encode(f"{email}:{key}".encode()).decode()

ENDPOINTS = [
    ("legacy domestic/search",
     "https://epc.opendatacommunities.org/api/v1/domestic/search"),
    ("new api domestic/search",
     "https://epc.opendatacommunities.org/api/v1/domestic/search"),
]
for label, url in ENDPOINTS[:1]:
    for accept in ("application/json", "text/csv"):
        r = requests.get(url, params={"postcode": "DE14 2EG", "size": 5},
                         headers={"Authorization": f"Basic {tok}", "Accept": accept},
                         timeout=30)
        body = r.text[:400].replace("\n", " ")
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        print(f"{label} accept={accept}")
        print(f"   {r.status_code} {r.headers.get('content-type')} len={len(r.text)}")
        print(f"   {body[:260]}\n")

# Is there a newer host? The service moved in recent years.
for host in ("https://epc.opendatacommunities.org/api/v1/domestic/search",
             "https://epc.opendatacommunities.org/docs/api/domestic"):
    try:
        r = requests.get(host, headers={"Accept": "text/html"}, timeout=20)
        print(f"{host} -> {r.status_code} {len(r.text)}")
    except requests.RequestException as e:
        print(f"{host} -> ERR {type(e).__name__}")
