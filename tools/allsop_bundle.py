"""Search Allsop's React bundle for the property-search API endpoint."""
import re, requests

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
URL = ("https://assets.allsop-cdn.co.uk/build/js/react/packages/platform/"
       "frontend/bundle-1aef6e8e37.js")
js = requests.get(URL, headers=HEADERS, timeout=60).text
print("bundle bytes:", len(js))

pats = {
    "api paths":     r'["\'](/api/[a-zA-Z0-9/_\-{}.]+)["\']',
    "absolute api":  r'["\'](https?://[a-z0-9.\-]*allsop[a-z0-9.\-]*/[a-zA-Z0-9/_\-]*)["\']',
    "search-ish":    r'["\'](/[a-zA-Z0-9/_\-]*(?:search|listing|lot|propert|auction)[a-zA-Z0-9/_\-]*)["\']',
    "graphql":       r'graphql',
}
for label, pat in pats.items():
    hits = sorted(set(re.findall(pat, js, re.I)))
    print(f"\n--- {label}: {len(hits)}")
    for h in hits[:25]:
        print("   ", h if isinstance(h, str) else h)
