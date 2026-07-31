"""Read Allsop's robots.txt verbatim — the results URL carries a query string,
so any Disallow pattern matching query params matters."""
import requests

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
r = requests.get("https://www.allsop.co.uk/robots.txt", headers=HEADERS, timeout=25)
print("status:", r.status_code)
print(r.text)

import urllib.robotparser as rp
p = rp.RobotFileParser()
p.parse(r.text.splitlines())
for url in ("/property-search?auction_id=abc&view=table",
            "/auctions/past-auction-results/",
            "/property-search"):
    print(f"can_fetch AuctionResearchBot {url!r}: {p.can_fetch('AuctionResearchBot', url)}")
