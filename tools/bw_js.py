"""Pull Bond Wolfe's search.js and find how it loads lots."""
import re, requests

HEADERS = {"User-Agent": "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"}
url = "https://www.bondwolfe.com/wp-content/themes/bwa/properties/js/search.js?ver=1.12"
js = requests.get(url, headers=HEADERS, timeout=30).text
print("len:", len(js))

for pat in (r"\$\.(?:get|post|ajax)\s*\(", r"url\s*:\s*[^,\n]+", r"action\s*:\s*[^,\n]+",
            r"fetch\s*\(", r"admin-ajax[^'\"]*", r"data\s*:\s*\{[^}]{0,140}"):
    for m in re.finditer(pat, js):
        s = max(0, m.start() - 90)
        print(f"\n--- {pat}\n{js[s:m.end()+180]}")
        break
