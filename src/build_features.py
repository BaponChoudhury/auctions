"""Assemble the modelling table: can area + condition + neighbourhood prices
predict what a lot sells for at auction?

Features are deliberately restricted to what is knowable BEFORE the hammer falls:
guide price, property type, area, condition from the listing text, and the
neighbourhood's recent sold prices from Land Registry. Nothing derived from the
outcome is allowed in, or the evaluation is meaningless.

  python build_features.py --lots ../data/*.jsonl --out ../data/features.csv
"""

import argparse
import bisect
import collections
import csv
import glob
import json
import pathlib
import statistics
import sys
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from enrich import classify_condition
from geo import load_cache
from ppd_match import C_DATE, C_PAON, C_POSTCODE, C_PRICE, C_TYPE, PPD_DIR


def sector_of(postcode: str) -> str | None:
    parts = (postcode or "").split()
    return f"{parts[0]} {parts[1][0]}" if len(parts) == 2 and parts[1] else None


def load_ppd_by_sector(sectors: set[str]) -> dict:
    """Sorted (date, price) per (sector, property_type) for as-at-date medians."""
    idx = collections.defaultdict(list)
    for path in sorted(PPD_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) <= C_PAON:
                    continue
                sec = sector_of(row[C_POSTCODE].strip().upper())
                if sec not in sectors:
                    continue
                try:
                    idx[(sec, row[C_TYPE])].append((row[C_DATE][:10], int(row[C_PRICE])))
                except ValueError:
                    continue
    for k in idx:
        idx[k].sort()
    print(f"PPD: {sum(len(v) for v in idx.values()):,} sales across "
          f"{len({k[0] for k in idx}):,} sectors", file=sys.stderr)
    return idx


def neighbourhood(idx: dict, sector: str, ptype: str | None, as_at: str,
                  months: int = 24) -> tuple[int | None, int, int | None]:
    """Median / count / IQR of nearby sales in the 24 months BEFORE the auction.

    Strictly before: using sales after the auction date would leak the future
    into a model meant to predict it.
    """
    if not (sector and as_at):
        return None, 0, None
    try:
        hi = date.fromisoformat(as_at)
    except ValueError:
        return None, 0, None
    lo = (hi - timedelta(days=30 * months)).isoformat()
    keys = [(sector, ptype)] if ptype else [(sector, t) for t in "DSTFO"]
    prices = []
    for k in keys:
        rows = idx.get(k)
        if not rows:
            continue
        i = bisect.bisect_left(rows, (lo, 0))
        j = bisect.bisect_left(rows, (hi.isoformat(), 0))
        prices += [p for _, p in rows[i:j]]
    if not prices:
        return None, 0, None
    prices.sort()
    med = int(statistics.median(prices))
    iqr = (prices[int(len(prices) * 0.75)] - prices[int(len(prices) * 0.25)]
           if len(prices) >= 4 else None)
    return med, len(prices), iqr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", nargs="+", required=True)
    ap.add_argument("--out", default="../data/features.csv")
    args = ap.parse_args()

    lots = []
    for pattern in args.lots:
        for path in glob.glob(pattern):
            with open(path, encoding="utf-8") as f:
                lots += [json.loads(l) for l in f if l.strip()]
    print(f"lots: {len(lots):,}", file=sys.stderr)

    geo = load_cache()
    sectors = {sector_of(l.get("postcode") or "") for l in lots}
    sectors.discard(None)
    idx = load_ppd_by_sector(sectors)

    rows, kept = [], 0
    for l in lots:
        # Only lots with a known outcome can be trained or scored against.
        if not l.get("hammer_price") or not l.get("auction_date"):
            continue
        sec = sector_of(l.get("postcode") or "")
        g = geo.get(l.get("postcode") or "") or {}
        cond, flags = classify_condition(l.get("description") or "")
        med, n, iqr = neighbourhood(idx, sec, l.get("property_type"), l["auction_date"])
        rows.append({
            "source": l["source"],
            "auction_date": l["auction_date"],
            "hammer_price": l["hammer_price"],
            "guide_price": l.get("guide_price") or "",
            "property_type": l.get("property_type") or "",
            "bedrooms": l.get("bedrooms") or "",
            "region": g.get("region") or "",
            "district": g.get("admin_district") or "",
            "sector": sec or "",
            "condition": cond,
            "flag_tenanted": int("tenanted" in flags),
            "flag_hmo": int("hmo" in flags),
            "flag_land": int("land_only" in flags),
            "comp_median": med if med else "",
            "comp_count": n,
            "comp_iqr": iqr if iqr else "",
        })
        kept += 1

    out = pathlib.Path(args.out)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    have_comp = sum(1 for r in rows if r["comp_median"] != "")
    have_guide = sum(1 for r in rows if r["guide_price"] != "")
    print(f"wrote {out} — {kept:,} lots with a known sale price")
    print(f"  with a neighbourhood comp: {have_comp:,} ({100*have_comp//kept}%)")
    print(f"  with a guide price:        {have_guide:,} ({100*have_guide//kept}%)")


if __name__ == "__main__":
    main()
