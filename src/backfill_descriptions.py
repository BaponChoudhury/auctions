"""Fetch full lot descriptions for lots that matter, to test whether condition
predicts price.

Condition is classified for only ~1% of the modelling table because full
descriptions were never fetched at scale. Rather than re-scrape everything, this
fetches descriptions only for lots that can actually enter the model — those
with a known sale price — and writes them back in place.

  python backfill_descriptions.py --lots ../data/sdl_all.jsonl --sold-only

SDL: ~1,500 priced lots at 3s ≈ 75 minutes.
"""

import argparse
import json
import sys
import time

import requests

from scrape_sdl import fetch_description as sdl_description


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def save(path, lots):
    with open(path, "w", encoding="utf-8") as f:
        for lot in lots:
            f.write(json.dumps(lot) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", required=True)
    ap.add_argument("--sold-only", action="store_true",
                    help="Only lots with a hammer price (the ones the model uses)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--save-every", type=int, default=100,
                    help="Write progress back to disk periodically so a long run "
                         "can be interrupted without losing everything")
    args = ap.parse_args()

    lots = load(args.lots)
    todo = [l for l in lots
            if l.get("lot_url")
            and not (l.get("description") or "").strip()
            and (l.get("hammer_price") if args.sold_only else True)]
    if args.limit:
        todo = todo[: args.limit]

    print(f"{len(lots):,} lots in file; {len(todo):,} need a description")
    if not todo:
        return
    print(f"estimated time: {len(todo) * 3 / 60:.0f} minutes at the 3s crawl delay")

    done = 0
    for i, lot in enumerate(todo, 1):
        try:
            lot["description"] = sdl_description(lot["lot_url"])
            done += bool(lot["description"])
        except Exception as e:
            print(f"  ! {lot.get('lot_url')}: {e}", file=sys.stderr)
        if i % args.save_every == 0:
            save(args.lots, lots)
            print(f"  {i}/{len(todo)} ({done} with text)", flush=True)
    save(args.lots, lots)
    print(f"done: {done}/{len(todo)} lots now carry a description")


if __name__ == "__main__":
    main()
