"""Check candidate auction houses: do they publish results, and do robots allow it?"""
import sys, time
import requests

UA = "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
           "Accept-Language": "en-GB,en;q=0.9"}

SITES = {
    "bond_wolfe":     "https://www.bondwolfe.com",
    "allsop":         "https://www.allsop.co.uk",
    "auction_house":  "https://www.auctionhouse.co.uk",
    "pugh":           "https://www.pugh-auctions.com",
    "clive_emson":    "https://www.cliveemson.co.uk",
    "network":        "https://www.networkauctions.co.uk",
    "barnett_ross":   "https://www.barnettross.co.uk",
    "savills":        "https://auctions.savills.co.uk",
}

BOTS = ("claudebot", "gptbot", "ccbot", "google-extended", "bytespider",
        "amazonbot", "applebot-extended", "meta-externalagent")


def robots(base):
    try:
        r = requests.get(base + "/robots.txt", headers=HEADERS, timeout=25)
    except requests.RequestException as e:
        return {"error": type(e).__name__}
    if r.status_code != 200:
        return {"status": r.status_code, "note": "no robots.txt"}
    txt = r.text
    low = txt.lower()

    # Which groups fully disallow, and does the wildcard group block anything?
    named = [b for b in BOTS if f"user-agent: {b}" in low]
    wildcard, blanket = [], False
    grp = None
    for line in low.splitlines():
        line = line.split("#")[0].strip()
        if line.startswith("user-agent:"):
            grp = line.split(":", 1)[1].strip()
        elif line.startswith("disallow:") and grp == "*":
            path = line.split(":", 1)[1].strip()
            if path == "/":
                blanket = True
            elif path:
                wildcard.append(path)
    return {"status": 200, "named_ai_bots": named, "wildcard_blanket_block": blanket,
            "wildcard_disallow_n": len(wildcard),
            "content_signal": next((l.strip() for l in txt.splitlines()
                                    if "content-signal" in l.lower()), None)}


def reachable(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        return r.status_code, len(r.text)
    except requests.RequestException as e:
        return type(e).__name__, 0


for name, base in SITES.items():
    print(f"\n=== {name}  {base}")
    print("  robots:", robots(base))
    print("  home  :", reachable(base))
    time.sleep(2)
