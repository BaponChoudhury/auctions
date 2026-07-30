"""Postcode → area lookup (local authority, region, coordinates).

The scrapers record a postcode but no area, which leaves two things broken:

  1. HPI time-adjustment. The hpi table is keyed by (area_code, month) and
     area_code is an ONS code. Without one per lot, every comp in the corpus gets
     adjusted by a single national index — a Lambeth flat and a Stoke terrace
     moved by the same ratio. `codes.admin_district` here IS that ONS code.
  2. Any grouping by town/region, which only existed inside the raw address text.

Source: postcodes.io — free, open (OGL), no key, bulk endpoint of 100 per call.
Results are cached to disk because postcode → area effectively never changes, so
a full corpus costs one pass and nothing thereafter.

  python geo.py --lots ../data/sdl_all.jsonl ../data/bw_all.jsonl
"""

import argparse
import json
import os
import pathlib
import sys
import time

import requests

API = "https://api.postcodes.io/postcodes"
BATCH = 100
DELAY_S = 1.0
CACHE = pathlib.Path(__file__).parent.parent / "data" / "postcode_geo.json"

FIELDS = ("admin_district", "admin_county", "admin_ward", "region", "country",
          "parliamentary_constituency", "lsoa", "latitude", "longitude")


def load_cache(path: pathlib.Path = CACHE) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict, path: pathlib.Path = CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _shape(res: dict) -> dict:
    out = {k: res.get(k) for k in FIELDS}
    codes = res.get("codes") or {}
    # E99999999 is postcodes.io's "not applicable" sentinel, not a real area.
    county = codes.get("admin_county")
    out["admin_district_code"] = codes.get("admin_district")
    out["admin_county_code"] = None if county in (None, "E99999999") else county
    return out


def lookup(postcodes, cache: dict | None = None, session=None, verbose=True) -> dict:
    """Resolve postcodes to area info, using and updating the on-disk cache."""
    cache = load_cache() if cache is None else cache
    todo = sorted({p for p in postcodes if p and p not in cache})
    if not todo:
        return cache
    session = session or requests.Session()
    if verbose:
        print(f"resolving {len(todo)} new postcodes ({len(cache)} cached)")

    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            r = session.post(API, json={"postcodes": chunk}, timeout=45)
            r.raise_for_status()
            results = r.json()["result"]
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  ! batch {i//BATCH}: {e}", file=sys.stderr)
            continue
        for item in results:
            res = item.get("result")
            # Cache misses too, as null — otherwise every run retries dead postcodes.
            cache[item["query"]] = _shape(res) if res else None
        if verbose:
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")
        time.sleep(DELAY_S)

    save_cache(cache)
    return cache


GEO_UPSERT = """
insert into postcode_geo (postcode, admin_district, admin_district_code, admin_county,
                          admin_county_code, admin_ward, region, country,
                          parliamentary_constituency, lsoa, latitude, longitude)
values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
on conflict (postcode) do update set
    admin_district = excluded.admin_district,
    admin_district_code = excluded.admin_district_code,
    admin_county = excluded.admin_county,
    admin_county_code = excluded.admin_county_code,
    admin_ward = excluded.admin_ward, region = excluded.region,
    country = excluded.country,
    parliamentary_constituency = excluded.parliamentary_constituency,
    lsoa = excluded.lsoa, latitude = excluded.latitude, longitude = excluded.longitude"""


def upsert_geo(conn, cache: dict) -> int:
    from psycopg2.extras import execute_batch
    rows = [(pc, g["admin_district"], g["admin_district_code"], g["admin_county"],
             g["admin_county_code"], g["admin_ward"], g["region"], g["country"],
             g["parliamentary_constituency"], g["lsoa"], g["latitude"], g["longitude"])
            for pc, g in cache.items() if g]
    with conn.cursor() as cur:
        execute_batch(cur, GEO_UPSERT, rows)
    conn.commit()
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", nargs="+", required=True, help="lots.jsonl file(s)")
    ap.add_argument("--to-db", action="store_true", help="Also upsert into postcode_geo")
    args = ap.parse_args()

    postcodes = set()
    for path in args.lots:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    pc = json.loads(line).get("postcode")
                    if pc:
                        postcodes.add(pc)
    print(f"{len(postcodes)} distinct postcodes across {len(args.lots)} file(s)")

    cache = lookup(postcodes)
    hit = sum(1 for p in postcodes if cache.get(p))
    print(f"resolved {hit}/{len(postcodes)} ({100*hit//len(postcodes)}%)")

    dist = {}
    for p in postcodes:
        g = cache.get(p)
        if g:
            dist[g["admin_district"]] = dist.get(g["admin_district"], 0) + 1
    print(f"distinct local authorities: {len(dist)}")
    for name, n in sorted(dist.items(), key=lambda x: -x[1])[:10]:
        print(f"  {name:28} {n}")

    if args.to_db:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        print(f"upserted {upsert_geo(conn, cache)} rows into postcode_geo")
        conn.close()


if __name__ == "__main__":
    main()
