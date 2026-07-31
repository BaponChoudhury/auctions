"""Source assessment: underthehammer.com (aggregator). Run 2026-07-31.

Conclusion: no robots-permitted route to the lot data for our own bot.

  * robots.txt Allows /properties, /property/, /auctions for `User-agent: *`
    but Disallows /api/ for "regular crawlers" (their words).
  * Those allowed pages are client-rendered shells — 57-70 characters of text,
    zero £ amounts, no lot fields in the payload. All content arrives via /api/.
  * sitemap.xml has 131 entries and NO /property/ pages, so there is no lot
    inventory exposed there either.
  * Their terms-of-use / acceptable-use-policy are themselves rendered from
    /api/, so we could not read what they permit — which is the thing that
    should gate any decision here.
  * They explicitly welcome named AI crawlers (GPTBot, ChatGPT-User, Claude-Web,
    anthropic-ai, Google-Extended) and grant those agents /api/ai/. That
    allowance is for those named agents, not for this pipeline's bot, and
    spoofing one of those user-agents to claim it would be dishonest.

Also worth weighing: it is an aggregator. Its value is a compiled database,
which attracts UK database right far more strongly than the individual facts on
an originating auction house's own site — and we can reach those houses directly
anyway, fresher and with no intermediary terms.

If this source is wanted, the route is to ask them (they publish a /products
page), not to scrape it.
"""

import re
import urllib.robotparser as rp

import requests
from bs4 import BeautifulSoup

BASE = "https://www.underthehammer.com"
UA = "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}


def main() -> None:
    txt = requests.get(f"{BASE}/robots.txt", headers=HEADERS, timeout=30).text
    agents = re.findall(r"(?im)^user-agent:\s*(.+)$", txt)
    print("robots.txt user-agent groups:", agents)

    p = rp.RobotFileParser()
    p.parse(txt.splitlines())
    print(f"\nwhat {UA.split('/')[0]} may fetch:")
    for path in ("/", "/properties", "/property/1", "/auctions", "/api/", "/api/ai/"):
        print(f"  {path:14} {p.can_fetch(UA, BASE + path)}")

    print("\nis the lot data actually in the allowed pages?")
    for path in ("/properties", "/auctions"):
        html = requests.get(BASE + path, headers=HEADERS, timeout=30).text
        text = re.sub(r"\s+", " ",
                      BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        print(f"  {path:12} {len(html):6} bytes payload, "
              f"{len(text):4} chars of text, "
              f"{len(re.findall(r'£[\\d,]{4,}', html))} prices")

    locs = re.findall(r"<loc>([^<]+)</loc>",
                      requests.get(f"{BASE}/sitemap.xml", headers=HEADERS, timeout=30).text)
    print(f"\nsitemap: {len(locs)} entries, "
          f"{len([u for u in locs if '/property/' in u])} lot pages")


if __name__ == "__main__":
    main()
