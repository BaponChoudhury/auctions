"""Recover sale prices from Land Registry Price Paid Data.

Roughly 45% of auction lots publish no price: houses disclose a figure only for
lots sold AT auction, never for "sold prior" / "sold after". But every completed
residential sale in England & Wales is registered, so the price can often be
recovered by matching a lot to its PPD transaction on

    postcode  +  house number (PAON)  +  a completion date shortly after the auction

Auction completion is typically 20-28 days after the hammer, so the default
window is -30..+120 days around the auction date. `--window-report` prints the
observed lag distribution rather than trusting that assumption.

Honest limits, all measured by --report rather than assumed:
  * PPD is England & Wales only. Scottish lots can never match.
  * PPD is RESIDENTIAL only. Commercial lots (much of Allsop) can never match.
  * PPD lags completion by 1-2 months, so the most recent auctions are absent.
  * A lot needs a house number; named buildings and land parcels have no PAON
    number to match on.
  * The registered price is the completion price. It can legitimately differ
    from the hammer price, which is why --validate compares the two on lots
    where both are known.

  python ppd_match.py --lots ../data/*.jsonl --validate
"""

import argparse
import collections
import csv
import glob
import json
import pathlib
import re
import statistics
import sys
from datetime import date, timedelta

from common import house_number

PPD_DIR = pathlib.Path(__file__).parent.parent / "data" / "ppd"

# Official column order: id, price, date, postcode, type, new, tenure,
# paon, saon, street, locality, town, district, county, category, status
C_PRICE, C_DATE, C_POSTCODE, C_TYPE, C_PAON, C_SAON = 1, 2, 3, 4, 7, 8

_NUM_RE = re.compile(r"(\d+[a-z]?)", re.I)


def paon_number(paon: str) -> str | None:
    """PPD's PAON is not always a bare number: 'LIME COURT, 114' is common."""
    m = _NUM_RE.search(paon or "")
    return m.group(1).lower() if m else None


def load_ppd(postcodes: set[str], paths) -> dict:
    """Stream the extracts, keeping only rows in postcodes we actually hold."""
    index = collections.defaultdict(list)
    scanned = kept = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                scanned += 1
                if len(row) <= C_SAON:
                    continue
                pc = row[C_POSTCODE].strip().upper()
                if pc not in postcodes:
                    continue
                try:
                    price = int(row[C_PRICE])
                except ValueError:
                    continue
                index[pc].append({
                    "price": price,
                    "date": row[C_DATE][:10],
                    "paon": row[C_PAON],
                    "paon_no": paon_number(row[C_PAON]),
                    "saon": row[C_SAON],
                    "type": row[C_TYPE],
                })
                kept += 1
    print(f"scanned {scanned:,} PPD rows, kept {kept:,} in {len(index):,} "
          f"corpus postcodes", file=sys.stderr)
    return index


def coverage_horizon(paths) -> str:
    """Latest transfer_date present. PPD lags completion by 1-2 months, so
    anything auctioned near this date cannot have been registered yet."""
    latest = ""
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) > C_DATE:
                    d = row[C_DATE][:10]
                    if d > latest:
                        latest = d
    return latest


def candidates(lot: dict, index: dict, before: int, after: int) -> list[dict]:
    """PPD sales for this exact property completing near the auction date."""
    pc = (lot.get("postcode") or "").upper()
    hn = house_number(lot.get("address_raw", ""))
    adate = lot.get("auction_date")
    if not (pc and hn and adate and pc in index):
        return []
    try:
        a = date.fromisoformat(adate)
    except ValueError:
        return []
    lo, hi = a - timedelta(days=before), a + timedelta(days=after)
    out = []
    for sale in index[pc]:
        if sale["paon_no"] != hn:
            continue
        try:
            d = date.fromisoformat(sale["date"])
        except ValueError:
            continue
        if lo <= d <= hi:
            out.append({**sale, "lag_days": (d - a).days})
    return sorted(out, key=lambda s: abs(s["lag_days"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", nargs="+", required=True)
    ap.add_argument("--ppd", nargs="*", help="PPD csv paths (default: data/ppd/*.csv)")
    # Defaults chosen by sweeping the window against lots whose hammer price IS
    # published (tools/ppd_sweep.py), not by assumption:
    #   before=30 -> 78% exact   before=0 -> 92% exact, only 5% fewer matches.
    # A pre-auction window is almost pure false positives: it matches the PREVIOUS
    # owner's purchase, which is why those matches skewed low (median -£10,000).
    #   after=120 -> 92%   after=90 -> 93%   after=60 -> 96%   after=45 -> 97%
    # 90 keeps recall while dropping the long tail of unrelated later sales.
    ap.add_argument("--before", type=int, default=0)
    ap.add_argument("--after", type=int, default=90)
    ap.add_argument("--validate", action="store_true",
                    help="Compare recovered prices against known hammer prices")
    ap.add_argument("--out", help="Write lots with a recovered_price field")
    args = ap.parse_args()

    lots = []
    for pattern in args.lots:
        for path in glob.glob(pattern):
            with open(path, encoding="utf-8") as f:
                lots += [json.loads(l) for l in f if l.strip()]
    print(f"lots: {len(lots):,}")

    ppd_paths = args.ppd or sorted(str(p) for p in PPD_DIR.glob("*.csv"))
    if not ppd_paths:
        sys.exit(f"no PPD csv found in {PPD_DIR} — run tools/ppd_download.py first")
    postcodes = {(l.get("postcode") or "").upper() for l in lots if l.get("postcode")}
    index = load_ppd(postcodes, ppd_paths)

    matched = unmatched = 0
    recovered = 0
    lags, diffs, exact = [], [], 0
    for lot in lots:
        hits = candidates(lot, index, args.before, args.after)
        lot["ppd_matches"] = len(hits)
        best = hits[0] if hits else None
        lot["recovered_price"] = best["price"] if best else None
        lot["recovered_lag_days"] = best["lag_days"] if best else None
        # A match on a lot that did NOT sell at auction is not an auction result.
        # It is a later private sale, which is useful but a different fact — do
        # not let it be read as the hammer price.
        lot["recovered_kind"] = (
            None if not best else
            "auction_completion" if lot.get("status") in ("sold", "sold_prior", "sold_after")
            else "later_sale")
        # More than one candidate sale in the window: the pick is a guess.
        lot["recovered_ambiguous"] = bool(best and len(hits) > 1)
        if best:
            matched += 1
            lags.append(best["lag_days"])
            if lot.get("hammer_price"):
                d = best["price"] - lot["hammer_price"]
                diffs.append(d)
                exact += (d == 0)
            elif lot["recovered_kind"] == "auction_completion":
                recovered += 1
        else:
            unmatched += 1

    eligible = [l for l in lots if l.get("postcode") and l.get("auction_date")
                and house_number(l.get("address_raw", ""))]
    print(f"\nmatchable at all (postcode + house no + date): {len(eligible):,}"
          f" ({100*len(eligible)//len(lots)}%)")
    print(f"matched to a PPD sale: {matched:,} "
          f"({100*matched//max(len(eligible),1)}% of matchable)")
    print(f"  NEW auction prices recovered (sold lot, no published figure): {recovered:,}")
    later = sum(1 for l in lots if l.get("recovered_kind") == "later_sale")
    ambig = sum(1 for l in lots if l.get("recovered_ambiguous"))
    print(f"  later private sales of lots that did NOT sell at auction: {later:,}")
    print(f"  ambiguous (more than one candidate sale in window): {ambig:,}")

    # A raw match rate is misleading: lots that did not sell SHOULD never match,
    # and PPD only covers the years actually downloaded.
    years = sorted({p.rsplit("-", 1)[1][:4] for p in
                    (str(x) for x in ppd_paths)} - {""})
    lo_year, hi_year = min(years), max(years)
    print(f"\nPPD extracts loaded cover {lo_year}-{hi_year}")

    def rate(rows):
        if not rows:
            return "        n/a"
        m = sum(1 for l in rows if l["recovered_price"] is not None)
        return f"{m:5,}/{len(rows):5,}  {100*m//len(rows):3}%"

    in_range = [l for l in eligible
                if l.get("auction_date", "")[:4] >= lo_year
                and l.get("auction_date", "")[:4] <= hi_year]
    print(f"  eligible lots inside that range: {len(in_range):,} "
          f"(of {len(eligible):,} eligible)")

    print("\nmatch rate by status (only sold lots SHOULD match):")
    by_status = collections.defaultdict(list)
    for l in in_range:
        by_status[l.get("status", "?")].append(l)
    for status in sorted(by_status, key=lambda s: -len(by_status[s])):
        print(f"  {status:12} {rate(by_status[status])}")

    sold_states = ("sold", "sold_prior", "sold_after")
    truly_sold = [l for l in in_range if l.get("status") in sold_states]
    print(f"\n  ALL sold statuses in range: {rate(truly_sold)}")

    print("\nmatch rate by source:")
    by_src = collections.defaultdict(list)
    for l in in_range:
        if l.get("status") in sold_states:
            by_src[l.get("source", "?")].append(l)
    for src in sorted(by_src, key=lambda s: -len(by_src[s])):
        print(f"  {src:12} {rate(by_src[src])}")

    if lags:
        lags.sort()
        print(f"\ncompletion lag after auction (days): median {statistics.median(lags):.0f}, "
              f"p10 {lags[len(lags)//10]}, p90 {lags[9*len(lags)//10]}")

    # The single most misread number here: a low match rate on recent auctions is
    # PPD's registration lag, not a broken matcher.
    horizon = coverage_horizon(ppd_paths)
    cutoff = (date.fromisoformat(horizon) - timedelta(days=int(statistics.median(lags))
                                                      if lags else 29)).isoformat()
    recent = [l for l in eligible if (l.get("auction_date") or "") > cutoff
              and l.get("status") in sold_states]
    print(f"\nPPD reaches {horizon}; the final month or two is always partial.")
    print(f"  auctions after ~{cutoff} cannot be matched yet: "
          f"{len(recent):,} sold lots are simply too recent.")

    if args.validate and diffs:
        diffs_sorted = sorted(diffs)
        within = sum(1 for d in diffs if abs(d) <= 1000)
        print(f"\nvalidation against {len(diffs):,} lots where the hammer price IS published:")
        print(f"  exact match          {exact:,} ({100*exact//len(diffs)}%)")
        print(f"  within £1,000        {within:,} ({100*within//len(diffs)}%)")
        print(f"  median difference    £{statistics.median(diffs_sorted):,.0f}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for lot in lots:
                f.write(json.dumps(lot) + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
