"""Plain answer to: 'what does a <type> with <beds> beds go for around here?'

Widens the search automatically until there is enough data to say anything, and
tells you which level it actually answered from. If it had to widen a lot, that
is the honest signal that the local sample is too thin.

  python price_it.py --type D --beds 2 --outcode ST16 ST17
"""

import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from geo import load_cache

DATA = pathlib.Path(__file__).parent.parent / "data"
NAME = {"D": "detached house", "S": "semi-detached house", "T": "terraced house",
        "F": "flat", "O": "land/commercial"}
STAFFS = {"Stafford", "Stone", "Cannock Chase", "South Staffordshire",
          "Newcastle-under-Lyme", "Staffordshire Moorlands", "East Staffordshire",
          "Lichfield", "Tamworth", "Stoke-on-Trent"}


def outcode(pc):
    p = (pc or "").split()
    return p[0] if len(p) == 2 else ""


def band(prices):
    a = np.array(sorted(prices))
    return {"n": len(a), "p25": np.percentile(a, 25), "med": np.percentile(a, 50),
            "p75": np.percentile(a, 75), "p10": np.percentile(a, 10),
            "p90": np.percentile(a, 90)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True, help="D/S/T/F/O")
    ap.add_argument("--beds", type=int)
    ap.add_argument("--outcode", nargs="+", default=["ST16", "ST17"])
    args = ap.parse_args()

    geo = load_cache()
    lots = []
    for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
        f = DATA / f"{p}.jsonl"
        if f.exists():
            lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
    for l in lots:
        g = geo.get(l.get("postcode") or "") or {}
        l["district"] = g.get("admin_district")
        l["outcode"] = outcode(l.get("postcode"))

    sold = [l for l in lots if l["hammer_price"] and l.get("property_type") == args.type]
    want = set(args.outcode)
    nearby = {o[:3] for o in want}          # ST16/ST17 -> "ST1" family

    # Progressively wider searches. Stop at the first with enough sales.
    LEVELS = [
        (f"{'/'.join(sorted(want))} exactly",
         [l for l in sold if l["outcode"] in want]),
        (f"{'/'.join(sorted(want))} + neighbouring outcodes",
         [l for l in sold if l["outcode"][:3] in nearby]),
        ("Staffordshire as a whole",
         [l for l in sold if l["district"] in STAFFS]),
        ("everywhere we have data",
         sold),
    ]

    print("=" * 68)
    label = NAME.get(args.type, args.type)
    beds = f"{args.beds}-bed " if args.beds else ""
    print(f"  {beds}{label} — {'/'.join(sorted(want))}")
    print("=" * 68)

    answered = False
    for name, group in LEVELS:
        if args.beds:
            group = [l for l in group if l.get("bedrooms") == args.beds]
        n = len(group)
        flag = "" if n >= 8 else "  (too thin to quote)"
        print(f"\n  {name:44} {n:4} sales{flag}")
        if n >= 8 and not answered:
            b = band([l["hammer_price"] for l in group])
            print(f"\n  {'-'*62}")
            print(f"  ANSWER, based on {b['n']} sales at this level:")
            print(f"    most sell between   £{b['p25']:,.0f} and £{b['p75']:,.0f}")
            print(f"    typical             £{b['med']:,.0f}")
            print(f"    bargain end         £{b['p10']:,.0f}")
            print(f"    top end             £{b['p90']:,.0f}")
            print(f"  {'-'*62}")
            answered = True
            recent = sorted(group, key=lambda l: l["auction_date"] or "",
                            reverse=True)[:6]
            print("\n  most recent examples:")
            for l in recent:
                bd = f"{l['bedrooms']}bed" if l.get("bedrooms") else "  ?  "
                print(f"    {l['auction_date']}  {bd:5} £{l['hammer_price']:>8,}  "
                      f"{l['address_raw'][:40]}")

    if not answered:
        print("\n  Not enough sales at any level to give a range for this "
              "combination.")
    print()


if __name__ == "__main__":
    main()
