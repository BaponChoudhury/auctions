"""Authoritative inventory: what data do we actually hold right now?"""
import collections, json, os, pathlib, sys

sys.path.insert(0, "../src")
DATA = pathlib.Path("../data")

rows, files = [], []
for p in sorted(DATA.glob("*.jsonl")):
    n = sum(1 for line in open(p, encoding="utf-8") if line.strip())
    files.append((p.name, n, p.stat().st_size))

print("scraped files on disk:")
for name, n, size in files:
    print(f"  {name:22} {n:6} lots  {size/1e6:6.2f} MB")

# The corpus proper — the two full backfills, not the intermediate test files.
corpus = ["sdl_all.jsonl", "bw_all.jsonl"]
for name in corpus:
    rows += [json.loads(l) for l in open(DATA / name, encoding="utf-8") if l.strip()]

print(f"\n=== CORPUS ({' + '.join(corpus)}) ===")
src = collections.Counter(r["source"] for r in rows)
print(f"lots        {len(rows)}")
print(f"sources     {len(src)}  -> {dict(src)}")
ev = collections.defaultdict(set)
for r in rows:
    if r["auction_date"]:
        ev[r["source"]].add(r["auction_date"])
print(f"auctions    {sum(len(v) for v in ev.values())}  -> "
      f"{ {k: len(v) for k, v in ev.items()} }")
dates = [r["auction_date"] for r in rows if r["auction_date"]]
print(f"date range  {min(dates)} to {max(dates)}")

sold = [r for r in rows if r["hammer_price"]]
print(f"\nwith a published sale price  {len(sold)} ({100*len(sold)//len(rows)}%)")
print(f"total hammer value           GBP {sum(r['hammer_price'] for r in sold):,}")
print(f"distinct postcodes           {len({r['postcode'] for r in rows if r['postcode']})}")
print(f"distinct postcode sectors    {len({r['postcode_sector'] for r in rows if r['postcode_sector']})}")

try:
    from geo import load_cache
    geo = load_cache()
    ok = {k: v for k, v in geo.items() if v}
    print(f"postcodes resolved to area   {len(ok)} of {len(geo)}")
    print(f"distinct local authorities   {len({v['admin_district'] for v in ok.values()})}")
    print(f"distinct regions             {len({v['region'] for v in ok.values()})}")
except Exception as e:
    print("geo cache unavailable:", e)

print("\n=== REFERENCE SOURCES ===")
for label, path, note in [
    ("postcodes.io (area)", DATA / "postcode_geo.json", "resolved + cached"),
    ("Land Registry PPD",   DATA / "ppd.csv",           "needed for comps + prior sales"),
    ("UK HPI",              DATA / "hpi.csv",           "needed to time-adjust comps"),
]:
    have = path.exists()
    print(f"  {label:22} {'LOADED' if have else 'NOT LOADED':11} {note}")
print(f"  {'EPC register API':22} "
      f"{'CONFIGURED' if os.environ.get('EPC_KEY') else 'NO KEY':11} floor area, age, UPRN")
print(f"  {'Postgres / Supabase':22} "
      f"{'SET' if os.environ.get('DATABASE_URL') else 'NOT SET':11} nothing is in a database yet")
