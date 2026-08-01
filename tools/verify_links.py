"""Pull the FULL lot URLs for Stafford-area unsold lots and check each one
actually resolves. Printing a truncated URL is worse than printing none."""
import json, pathlib, sys, time
import requests

sys.path.insert(0, "../src")
DATA = pathlib.Path("../data")
HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)",
           "Accept": "text/html,application/xhtml+xml"}
STAFF_OUT = {"ST15", "ST16", "ST17", "ST18", "ST19", "ST20", "ST21"}
LIVE = ("unsold", "listed", "postponed")


def outcode(pc):
    p = (pc or "").split()
    return p[0] if len(p) == 2 else ""


lots = []
for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
    f = DATA / f"{p}.jsonl"
    if f.exists():
        lots += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]

cand = [l for l in lots
        if outcode(l.get("postcode")) in STAFF_OUT and l["status"] in LIVE]
cand.sort(key=lambda l: l["auction_date"] or "", reverse=True)
print(f"{len(cand)} Stafford-area lots with no sale recorded\n")

s = requests.Session(); s.headers.update(HEADERS)
for l in cand[:14]:
    url = l["lot_url"]
    code = "?"
    try:
        r = s.get(url, timeout=30, allow_redirects=True)
        code = r.status_code
        if code == 200 and ("not found" in r.text.lower()[:4000]
                            or "no longer available" in r.text.lower()[:4000]):
            code = "200 but page says gone"
    except requests.RequestException as e:
        code = type(e).__name__
    time.sleep(3)
    print(f"[{code}] {l['auction_date']}  {l['status']:9} {l['address_raw'][:44]}")
    print(f"        {url}")
