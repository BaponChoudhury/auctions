"""Record predictions BEFORE an auction, score them after. A real forward test.

Backtests flatter a model: the split is chosen after the fact and every feature
already exists. This locks a prediction to a timestamp and a named lot, then
scores it against the published result once the auction has run.

  python forward_test.py --record          # find live lots, predict, append
  python forward_test.py --list            # show the open log
  python forward_test.py --score           # score any whose date has passed

The log is data/predictions.csv, append-only. A recorded row is never edited -
if a prediction was wrong it stays wrong, which is the point.
"""

import argparse
import csv
import json
import pathlib
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache
from predict_lot import (CATS, FEATURES, NAME, build_model, comps,
                         ppd_sector_index, reliability, sector_of)

ROOT = pathlib.Path(__file__).parent.parent
DATA = ROOT / "data"
LOG = DATA / "predictions.csv"
UPLIFT_LO, UPLIFT_MID, UPLIFT_HI = 1.10, 1.20, 1.49

FIELDS = ["recorded_at", "lot_id", "address", "postcode", "type", "beds",
          "guide", "auction_date", "house", "format", "model_point",
          "model_lo", "model_hi", "consensus_lo", "consensus_hi",
          "reliability", "note", "actual_hammer", "actual_status", "scored_at"]

# Live Stafford-area auction lots, read from auction-house sites and the
# Rightmove auction filter on 2026-08-01. `format` matters: the x1.20 uplift and
# the discount model were measured on UNCONDITIONAL auctions only.
SEED_LOTS = [
    dict(lot_id="sdl-51522", address="Cherry Arbour, The Rank, Gnosall, Stafford",
         postcode="ST20 0BU", type="D", beds=None, guide=230000,
         auction_date="2026-08-26", house="SDL", format="unconditional",
         note="detached bungalow"),
    dict(lot_id="uth-byron-close", address="12 Byron Close, Stafford",
         postcode="ST16 3NY", type="S", beds=3, guide=34000,
         auction_date="2026-08-12", house="Under The Hammer",
         format="unconditional",
         note="vacant freehold; guide far below local band - check legal pack"),
    dict(lot_id="bjb-sandon-road", address="Sandon Road, Stafford (block of 3)",
         postcode="ST16 3ES", type="T", beds=8, guide=240000,
         auction_date="", house="Butters John Bee", format="unconditional",
         note="MULTI-UNIT - per-property model does not apply"),
    dict(lot_id="pat-albert-terrace", address="Albert Terrace, Stafford",
         postcode="ST16 3EX", type="T", beds=3, guide=100000,
         auction_date="", house="Pattinson", format="secure-sale",
         note="tenanted GBP 545pcm; conditional format, reservation fee on top"),
    dict(lot_id="pat-john-amery", address="John Amery Drive, Stafford",
         postcode="ST17 9PE", type="T", beds=2, guide=135000,
         auction_date="", house="Pattinson", format="secure-sale",
         note="conditional format"),
    dict(lot_id="dbr-prospect-road", address="Prospect Road, Beaconside, Stafford",
         postcode="ST16 3", type="T", beds=3, guide=130000,
         auction_date="", house="D B Roberts", format="modern-method",
         note="MMoA; reservation fee on top"),
    dict(lot_id="dbr-bellasis-st", address="Bellasis Street, Stafford",
         postcode="ST16 3", type="T", beds=2, guide=110000,
         auction_date="", house="D B Roberts", format="modern-method",
         note="MMoA; reservation fee on top"),
]


def load_log():
    if not LOG.exists():
        return []
    with LOG.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_log(rows):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def predict(lot, model, err, geo, ppd_cache):
    """Model point + interval, and the consensus with guide and comparables."""
    pc = (lot["postcode"] or "").upper().strip()
    sector = sector_of(pc)
    if not sector:                      # partial postcode: use the outcode's 0 sector
        sector = f"{pc.split()[0]} {pc.split()[1]}" if len(pc.split()) == 2 else None
    if not sector:
        return None
    if sector not in ppd_cache:
        ppd_cache[sector] = ppd_sector_index({sector})
    med, cnt, iqr = comps(ppd_cache[sector], sector, lot["type"],
                          date.today().isoformat())
    if med is None:
        return None
    g = geo.get(pc) or {}
    row = pd.DataFrame([{"comp_median": med, "comp_count": cnt,
                         "comp_iqr": iqr if iqr else np.nan,
                         "bedrooms": lot.get("beds") or np.nan,
                         "property_type": lot["type"],
                         "region": g.get("region") or "",
                         "district": g.get("admin_district") or ""}])
    for c in CATS:
        row[c] = row[c].astype("category")
    point = float(np.exp(model.predict(row[FEATURES + CATS])[0]))
    lo = point / np.percentile(err, 75)
    hi = point / np.percentile(err, 25)

    lows, highs = [lo], [hi]
    if lot.get("guide") and lot.get("format") == "unconditional":
        lows.append(lot["guide"] * UPLIFT_LO)
        highs.append(lot["guide"] * UPLIFT_HI)
    c_lo, c_hi = max(lows), min(highs)
    if c_lo > c_hi:                     # no overlap: keep the widest honest span
        c_lo, c_hi = min(lows), max(highs)
    flag, _ = reliability(point, med)
    return point, lo, hi, c_lo, c_hi, flag


def cmd_record(args):
    df = pd.read_csv(DATA / "features.csv")
    df = df[(df.hammer_price > 1000) & df.property_type.isin(["D", "S", "T", "F"])]
    model, err, _, n_te, mdape = build_model(df)
    print(f"model trained; median absolute error {mdape:.0f}% on {n_te:,} unseen lots")

    geo = load_cache()
    rows = load_log()
    seen = {r["lot_id"] for r in rows}
    ppd_cache = {}
    added = 0
    for lot in SEED_LOTS:
        if lot["lot_id"] in seen:
            continue
        p = predict(lot, model, err, geo, ppd_cache)
        if p is None:
            print(f"  ! {lot['lot_id']}: no Land Registry comps, skipped")
            continue
        point, lo, hi, c_lo, c_hi, flag = p
        rows.append({**lot,
                     "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                     "model_point": round(point), "model_lo": round(lo),
                     "model_hi": round(hi), "consensus_lo": round(c_lo),
                     "consensus_hi": round(c_hi), "reliability": flag,
                     "actual_hammer": "", "actual_status": "", "scored_at": ""})
        added += 1
        warn = "" if flag == "OK" else f"   << {flag}"
        print(f"  recorded {lot['lot_id']:22} £{point:>9,.0f}  "
              f"(£{c_lo:,.0f}-£{c_hi:,.0f}){warn}")
    save_log(rows)
    print(f"\n{added} new prediction(s); {len(rows)} in {LOG}")


def cmd_list(args):
    rows = load_log()
    if not rows:
        print("no predictions recorded yet - run with --record")
        return
    today = date.today().isoformat()
    print(f"{'lot':22} {'auction':11} {'guide':>9} {'predicted':>10} "
          f"{'range':>21} {'status':>10}")
    for r in sorted(rows, key=lambda x: x["auction_date"] or "9999"):
        due = r["auction_date"] or "—"
        if r["actual_hammer"]:
            state = f"£{int(r['actual_hammer']):,}"
        elif due != "—" and due < today:
            state = "DUE - score"
        else:
            state = "pending"
        rng = f"£{int(r['consensus_lo']):,}-£{int(r['consensus_hi']):,}"
        guide = f"£{int(r['guide']):,}" if r["guide"] else "—"
        print(f"{r['lot_id'][:22]:22} {due:11} {guide:>9} "
              f"£{int(r['model_point']):>9,} {rng:>21} {state:>10}")
        if r["format"] != "unconditional":
            print(f"{'':22} ^ {r['format']} - model does not strictly apply")
        if r.get("reliability") and r["reliability"] != "OK":
            print(f"{'':22} ^ model {r['reliability']} in this price band")


def cmd_score(args):
    """Compare recorded predictions against results now in the corpus."""
    rows = load_log()
    lots = []
    for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
        f = DATA / f"{p}.jsonl"
        if f.exists():
            lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
    by_pc = {}
    for l in lots:
        if l.get("postcode"):
            by_pc.setdefault(l["postcode"].upper(), []).append(l)

    today = date.today().isoformat()
    hits, scored = [], 0
    for r in rows:
        if r["actual_hammer"] or not r["auction_date"] or r["auction_date"] > today:
            continue
        cands = [l for l in by_pc.get(r["postcode"].upper(), [])
                 if l.get("auction_date") == r["auction_date"]]
        if not cands:
            continue
        best = cands[0]
        r["actual_hammer"] = best.get("hammer_price") or ""
        r["actual_status"] = best.get("status", "")
        r["scored_at"] = today
        scored += 1
        if best.get("hammer_price"):
            hits.append((r, best["hammer_price"]))
    save_log(rows)

    print(f"scored {scored} lot(s)")
    for r, actual in hits:
        pred = float(r["model_point"])
        inside = float(r["consensus_lo"]) <= actual <= float(r["consensus_hi"])
        print(f"  {r['lot_id']:22} predicted £{pred:>9,.0f}  actual £{actual:>9,}  "
              f"err {100*abs(pred-actual)/actual:5.1f}%  "
              f"{'IN range' if inside else 'OUTSIDE range'}")
    if not hits:
        print("  nothing to score yet - results are not in the corpus.")
        print("  Re-run the scrapers after each auction date, then score again.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--score", action="store_true")
    args = ap.parse_args()
    if args.record:
        cmd_record(args)
    elif args.score:
        cmd_score(args)
    else:
        cmd_list(args)


if __name__ == "__main__":
    main()
