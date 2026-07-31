"""Clive Emson: why did robots.txt 406, and is there a usable results section?"""
import re
import requests

BASE = "https://www.cliveemson.co.uk"
UA = "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"

VARIANTS = [
    ("bare UA only", {"User-Agent": UA}),
    ("UA + text/plain", {"User-Agent": UA, "Accept": "text/plain,*/*"}),
    ("UA + */*", {"User-Agent": UA, "Accept": "*/*"}),
    ("UA + html accept + lang", {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
                                 "Accept-Language": "en-GB,en;q=0.9"}),
    ("browser-ish UA", {"User-Agent": "Mozilla/5.0 (compatible; AuctionResearchBot/0.1; "
                                      "+mailto:mailahb2017@gmail.com)",
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        "Accept-Language": "en-GB,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate"}),
]

print("=== robots.txt under different request shapes ===")
for label, h in VARIANTS:
    try:
        r = requests.get(f"{BASE}/robots.txt", headers=h, timeout=30)
        print(f"  {label:24} {r.status_code}  {len(r.text):6} bytes  "
              f"{(r.headers.get('content-type') or '')[:24]}")
        if r.status_code == 200 and r.text.strip():
            print("    ---")
            for line in r.text.splitlines()[:30]:
                print("    ", line)
            break
    except requests.RequestException as e:
        print(f"  {label:24} ERR {type(e).__name__}")

print("\n=== does the site itself respond to the same shapes? ===")
for label, h in VARIANTS[:4]:
    try:
        r = requests.get(BASE, headers=h, timeout=30)
        print(f"  {label:24} {r.status_code}  {len(r.text):7} bytes")
    except requests.RequestException as e:
        print(f"  {label:24} ERR {type(e).__name__}")
