"""What do Rightmove and Zoopla permit? Check before assuming either way."""
import re
import urllib.robotparser as rp

import requests

UA = "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"
SITES = {
    "Rightmove": "https://www.rightmove.co.uk",
    "Zoopla": "https://www.zoopla.co.uk",
    "OnTheMarket": "https://www.onthemarket.com",
}
PATHS = ["/", "/property-for-sale/", "/find.html", "/for-sale/",
         "/property-for-sale/Stafford.html", "/api/"]

for name, base in SITES.items():
    print(f"\n{'='*62}\n{name}  {base}\n{'='*62}")
    try:
        r = requests.get(f"{base}/robots.txt", headers={"User-Agent": UA}, timeout=30)
    except requests.RequestException as e:
        print(f"  robots.txt ERR {type(e).__name__}")
        continue
    print(f"  robots.txt: {r.status_code}, {len(r.text)} bytes")
    if r.status_code != 200:
        continue
    txt = r.text
    agents = re.findall(r"(?im)^user-agent:\s*(.+)$", txt)
    print(f"  user-agent groups: {sorted(set(a.strip() for a in agents))[:12]}")

    p = rp.RobotFileParser()
    p.parse(txt.splitlines())
    print("  what our agent may fetch:")
    for path in PATHS:
        print(f"    {path:34} {p.can_fetch(UA, base + path)}")

    # Wildcard group disallows
    grp, dis = None, []
    for line in txt.lower().splitlines():
        line = line.split("#")[0].strip()
        if line.startswith("user-agent:"):
            grp = line.split(":", 1)[1].strip()
        elif line.startswith("disallow:") and grp == "*":
            v = line.split(":", 1)[1].strip()
            if v:
                dis.append(v)
    print(f"  wildcard Disallow rules: {len(dis)}")
    for d in dis[:14]:
        print(f"    {d}")
