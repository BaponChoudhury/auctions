"""EPC enrichment against the CURRENT API (the replacement service).

Correcting an earlier wrong conclusion in this project: the new service is not
bulk-download-only. It has a REST API, documented at
https://get-energy-performance-data.communities.gov.uk/api-technical-documentation

  base   https://api.get-energy-performance-data.communities.gov.uk
  auth   Authorization: Bearer <token>   (token is on your "my account" page
         once signed in to the service with GOV.UK One Login)
  rate   6,000 requests per 5 minutes per IP

Floor area needs two calls, because search returns certificate metadata only:

  1. GET /api/domestic/search?postcode=DE14+2EG   -> certificate numbers + addresses
  2. GET /api/certificate?certificate_number=...  -> the full certificate

Certificate JSON varies by schema (RdSAP versions etc.), so the floor area is
found by searching the payload for a key that looks like a total floor area
rather than assuming one fixed field name.

Set the token in .env as EPC_BEARER_TOKEN (never pass it on the command line —
it would land in your shell history).

  python epc_api.py --lots ../data/*.jsonl --out ../data/epc_cache.json
"""

import argparse
import collections
import glob
import json
import os
import pathlib
import re
import sys
import time

import requests
from dotenv import load_dotenv

from common import house_number

API = "https://api.get-energy-performance-data.communities.gov.uk"
CACHE = pathlib.Path(__file__).parent.parent / "data" / "epc_cache.json"
# Documented limit is 6,000 per 5 minutes (20/s). Stay well under it.
DELAY_S = 0.12

FLOOR_KEY = re.compile(r"total.?floor.?area", re.I)
AGE_KEY = re.compile(r"construction.?age.?band", re.I)
FORM_KEY = re.compile(r"built.?form", re.I)
TYPE_KEY = re.compile(r"property.?type", re.I)


def _find(payload, pattern):
    """Certificate schemas differ between RdSAP versions; search by key shape."""
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    stack.append(v)
                elif pattern.search(str(k)) and v not in (None, "", "NO DATA!"):
                    return v
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _num(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


class EpcClient:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
        })

    def _get(self, path, params, tries=4):
        for attempt in range(tries):
            r = self.s.get(API + path, params=params, timeout=45)
            if r.status_code == 429:      # documented: back off, do not hammer
                wait = 20 * (attempt + 1)
                print(f"  rate limited, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if r.status_code == 401:
                raise SystemExit("EPC API rejected the token (401). Sign in at "
                                 "https://get-energy-performance-data.communities.gov.uk/ "
                                 "and copy a fresh bearer token from your account page "
                                 "into .env as EPC_BEARER_TOKEN.")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            time.sleep(DELAY_S)
            return r.json()
        return None

    def search_postcode(self, postcode: str) -> list[dict]:
        out = self._get("/api/domestic/search", {"postcode": postcode})
        data = (out or {}).get("data") or []
        return data if isinstance(data, list) else []

    def certificate(self, number: str) -> dict | None:
        out = self._get("/api/certificate", {"certificate_number": number})
        return (out or {}).get("data")


def address_of(cert: dict) -> str:
    return " ".join(str(cert.get(f"addressLine{i}") or "") for i in range(1, 5)).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", nargs="+", required=True)
    ap.add_argument("--out", default=str(CACHE))
    ap.add_argument("--limit", type=int, help="Only process the first N postcodes")
    ap.add_argument("--sold-only", action="store_true",
                    help="Only lots with a hammer price (the ones the model uses)")
    args = ap.parse_args()

    for env in (pathlib.Path(__file__).parent.parent / ".env",
                pathlib.Path(r"C:\Users\bapon\autoPosting\.env")):
        if env.exists():
            load_dotenv(env)
    # An EPC_KEY issued by the OLD service still works as a bearer token on the
    # new API — verified against /api/domestic/search, which returns 200 and real
    # certificates for it. The email half is not used at all any more: sending
    # base64(email:key), or the old Basic scheme, is rejected with 403 "Bad
    # authentication header". So an existing key needs no re-registration.
    token = os.environ.get("EPC_BEARER_TOKEN") or os.environ.get("EPC_KEY")
    if not token:
        sys.exit(
            "No EPC credential found. Set either in .env:\n"
            "  EPC_KEY=...            (a key from the old service still works)\n"
            "  EPC_BEARER_TOKEN=...   (from your account page on the new service:\n"
            "                          https://get-energy-performance-data"
            ".communities.gov.uk/)")

    lots = []
    for pattern in args.lots:
        for path in glob.glob(pattern):
            with open(path, encoding="utf-8") as f:
                lots += [json.loads(l) for l in f if l.strip()]
    if args.sold_only:
        lots = [l for l in lots if l.get("hammer_price")]

    postcodes = sorted({(l.get("postcode") or "").upper() for l in lots if l.get("postcode")})
    if args.limit:
        postcodes = postcodes[: args.limit]
    print(f"{len(lots):,} lots across {len(postcodes):,} postcodes")

    out_path = pathlib.Path(args.out)
    cache = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    client = EpcClient(token)

    # A postcode holds ~55 certificates but a lot needs exactly one — the
    # certificate whose house number matches. Fetching them all would be ~437,000
    # requests (6 hours); fetching only matches is ~16,000 (about 15 minutes).
    wanted = collections.defaultdict(set)
    for l in lots:
        pc = (l.get("postcode") or "").upper()
        hn = house_number(l.get("address_raw", ""))
        if pc and hn:
            wanted[pc].add(hn)

    done = 0
    for i, pc in enumerate(postcodes, 1):
        if pc in cache:
            continue
        try:
            certs = client.search_postcode(pc)
        except requests.RequestException as e:
            print(f"  ! {pc}: {e}", file=sys.stderr)
            continue

        targets = wanted.get(pc, set())
        entries = []
        for c in certs:
            addr = address_of(c)
            hn = house_number(addr)
            entry = {
                "certificate": c.get("certificateNumber"),
                "address": addr,
                "house_no": hn,
                "uprn": c.get("uprn"),
                "rating": c.get("currentEnergyEfficiencyBand"),
                "registered": c.get("registrationDate"),
                "floor_area_m2": None, "age_band": None,
                "built_form": None, "epc_property_type": None,
            }
            # Only the full certificate carries floor area, so only pay for it
            # where this certificate could actually belong to one of our lots.
            if hn and hn in targets and entry["certificate"]:
                full = client.certificate(entry["certificate"])
                if full:
                    entry["floor_area_m2"] = _num(_find(full, FLOOR_KEY))
                    entry["age_band"] = _find(full, AGE_KEY)
                    entry["built_form"] = _find(full, FORM_KEY)
                    entry["epc_property_type"] = _find(full, TYPE_KEY)
            entries.append(entry)
        cache[pc] = entries
        done += 1
        if done % 50 == 0:
            out_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
            got = sum(1 for v in cache.values() for c in v if c["floor_area_m2"])
            print(f"  {i}/{len(postcodes)} postcodes, {got:,} certs with floor area",
                  flush=True)

    out_path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    certs = sum(len(v) for v in cache.values())
    area = sum(1 for v in cache.values() for c in v if c["floor_area_m2"])
    print(f"cached {len(cache):,} postcodes, {certs:,} certificates, "
          f"{area:,} with a floor area -> {out_path}")


if __name__ == "__main__":
    main()
