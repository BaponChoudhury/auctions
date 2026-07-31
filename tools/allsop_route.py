"""Find how the SPA builds a lot's public URL."""
import re, requests

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
js = requests.get("https://assets.allsop-cdn.co.uk/build/js/react/packages/platform/"
                  "frontend/bundle-1aef6e8e37.js", headers=HEADERS, timeout=60).text

for pat in (r'["\']lot-[a-z\-]*["\']', r'getLotUrl[^,;]{0,120}',
            r'["\']/lot[a-zA-Z0-9/_\-:{}\.]*["\']',
            r'lotUrl\s*[:=][^,;]{0,120}', r'buildLotU[^,;]{0,140}'):
    hits = sorted(set(re.findall(pat, js)))
    print(f"\n--- {pat}: {len(hits)}")
    for h in hits[:12]:
        print("   ", h[:140])

# How does a lot card link out?
for m in list(re.finditer(r'href:\s*["\']?/?lot', js))[:5]:
    print("\n...", re.sub(r"\s+", " ", js[max(0, m.start()-200):m.start()+220]), "...")
