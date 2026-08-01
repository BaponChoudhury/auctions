"""Attach EPC floor area / age band to lots from the BULK certificate download.

Why bulk and not the API: the Open Data Communities EPC search API was retired
on 30 May 2026. Its host now redirects to
get-energy-performance-data.communities.gov.uk, which requires GOV.UK One Login
and publishes bulk files only. So there is no unattended API route any more —
somebody has to sign in and download the file.

    1. Sign in at https://get-energy-performance-data.communities.gov.uk/
    2. Download the domestic certificates bulk file
    3. Unzip it into data/epc/  (the export is one certificates.csv per local
       authority, or a single large csv — both are handled)
    4. python epc_load.py --lots ../data/*.jsonl --out ../data/epc_cache.json

Matching is postcode + house number, the same rule as the PPD matcher, because
an EPC address is free text with the number at the front. Where a postcode has
exactly one certificate and the lot has no usable number, that is recorded as a
'fuzzy' match so it can be filtered out later.

The point of this is `floor_area_m2`: it turns every neighbourhood comp from
£/property into £/m², which is the obvious next feature for the price model.
"""

import argparse
import collections
import csv
import glob
import json
import pathlib
import re
import sys

from common import house_number

EPC_DIR = pathlib.Path(__file__).parent.parent / "data" / "epc"

# Column names in the bulk export. Kept as names, not indexes: unlike the PPD
# extract this file HAS a header row and the column order has changed between
# releases.
COLS = {
    "postcode": ("POSTCODE",),
    "address": ("ADDRESS", "ADDRESS1"),
    "floor_area": ("TOTAL_FLOOR_AREA",),
    "age_band": ("CONSTRUCTION_AGE_BAND",),
    "rating": ("CURRENT_ENERGY_RATING",),
    "property_type": ("PROPERTY_TYPE",),
    "built_form": ("BUILT_FORM",),
    "uprn": ("UPRN",),
    "lodgement": ("LODGEMENT_DATE", "INSPECTION_DATE"),
}


def _pick(header: list[str]) -> dict:
    """Map our field names onto whatever this release calls its columns."""
    idx = {}
    upper = [h.strip().upper() for h in header]
    for field, candidates in COLS.items():
        for c in candidates:
            if c in upper:
                idx[field] = upper.index(c)
                break
    missing = {"postcode", "address", "floor_area"} - set(idx)
    if missing:
        raise SystemExit(f"EPC file is missing expected columns: {missing}\n"
                         f"header was: {header[:12]}")
    return idx


def _num(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def load_certificates(paths, wanted: set[str]) -> dict:
    """postcode -> [certificate, ...] for postcodes we actually hold."""
    index = collections.defaultdict(list)
    scanned = kept = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            try:
                idx = _pick(next(reader))
            except StopIteration:
                continue
            for row in reader:
                scanned += 1
                if len(row) <= max(idx.values()):
                    continue
                pc = row[idx["postcode"]].strip().upper()
                if pc not in wanted:
                    continue
                addr = row[idx["address"]]
                index[pc].append({
                    "address": addr,
                    "house_no": house_number(addr),
                    "floor_area_m2": _num(row[idx["floor_area"]]),
                    "age_band": row[idx["age_band"]] if "age_band" in idx else None,
                    "rating": row[idx["rating"]] if "rating" in idx else None,
                    "epc_property_type": row[idx["property_type"]] if "property_type" in idx else None,
                    "built_form": row[idx["built_form"]] if "built_form" in idx else None,
                    "uprn": row[idx["uprn"]] if "uprn" in idx else None,
                    "lodged": row[idx["lodgement"]][:10] if "lodgement" in idx else None,
                })
                kept += 1
    print(f"scanned {scanned:,} certificates, kept {kept:,} in {len(index):,} "
          f"corpus postcodes", file=sys.stderr)
    return index


def match(lot: dict, index: dict) -> dict | None:
    """Best certificate for a lot: exact house-number match, else a lone cert."""
    pc = (lot.get("postcode") or "").upper()
    certs = index.get(pc)
    if not certs:
        return None
    hn = house_number(lot.get("address_raw", ""))
    if hn:
        exact = [c for c in certs if c["house_no"] == hn]
        if exact:
            # Most recent certificate wins if a property has several.
            best = max(exact, key=lambda c: c.get("lodged") or "")
            return {**best, "epc_match": "exact"}
    if len(certs) == 1:
        return {**certs[0], "epc_match": "fuzzy"}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", nargs="+", required=True)
    ap.add_argument("--epc", nargs="*", help="EPC csv paths (default data/epc/**/*.csv)")
    ap.add_argument("--out", default="../data/epc_cache.json")
    args = ap.parse_args()

    lots = []
    for pattern in args.lots:
        for path in glob.glob(pattern):
            with open(path, encoding="utf-8") as f:
                lots += [json.loads(l) for l in f if l.strip()]
    print(f"lots: {len(lots):,}")

    paths = args.epc or [str(p) for p in EPC_DIR.rglob("*.csv")]
    if not paths:
        sys.exit(f"No EPC csv found under {EPC_DIR}.\n"
                 "The EPC search API was retired on 30 May 2026. Sign in at\n"
                 "  https://get-energy-performance-data.communities.gov.uk/\n"
                 "download the domestic certificates bulk file, unzip into data/epc/,\n"
                 "then re-run.")

    wanted = {(l.get("postcode") or "").upper() for l in lots if l.get("postcode")}
    index = load_certificates(paths, wanted)

    out, exact, fuzzy = {}, 0, 0
    for lot in lots:
        m = match(lot, index)
        if not m:
            continue
        out[lot["source_lot_id"]] = {
            "floor_area_m2": m["floor_area_m2"], "age_band": m["age_band"],
            "rating": m["rating"], "built_form": m["built_form"],
            "uprn": m["uprn"], "epc_match": m["epc_match"],
        }
        exact += m["epc_match"] == "exact"
        fuzzy += m["epc_match"] == "fuzzy"

    pathlib.Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    with_area = sum(1 for v in out.values() if v["floor_area_m2"])
    print(f"matched {len(out):,}/{len(lots):,} lots "
          f"({exact:,} exact, {fuzzy:,} fuzzy)")
    print(f"  with a floor area: {with_area:,}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
