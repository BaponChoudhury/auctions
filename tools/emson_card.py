"""Dump one Clive Emson lot card so selectors come from fact."""
import re
from bs4 import BeautifulSoup

html = open("emson_probe.html", encoding="utf-8").read()
soup = BeautifulSoup(html, "html.parser")
lots = soup.select(".lot.activeLot")
print("lots:", len(lots))

text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
for cue in ("Sold", "Guide", "Withdrawn", "Unsold", "Available", "Lot"):
    print(f"  text '{cue}': {len(re.findall(cue, text, re.I))}")
print("  £ amounts in html:", len(re.findall(r"£[\d,]{3,}", html)))

if lots:
    c = lots[0]
    print("\n--- element inventory of lot 1 ---")
    seen = set()
    for e in c.find_all(True):
        cls = " ".join(e.get("class") or [])
        if not cls or cls in seen:
            continue
        seen.add(cls)
        t = re.sub(r"\s+", " ", e.get_text(" ", strip=True))[:76]
        print(f"  {e.name:6} .{cls[:44]:46} {t}")
    print("\n--- links ---")
    for a in c.select("a[href]")[:3]:
        print("   ", a["href"])
    print("\n--- raw ---")
    print(re.sub(r"\n\s*\n", "\n", c.prettify()[:1500]))

    print("\n--- status wording across all lots ---")
    import collections
    tally = collections.Counter()
    for l in lots:
        t = re.sub(r"\s+", " ", l.get_text(" ", strip=True))
        m = re.search(r"(Sold Prior|Sold After|Sold|Withdrawn|Unsold|Available|"
                      r"Postponed|Under Offer)", t, re.I)
        tally[m.group(1).title() if m else "(none)"] += 1
    print("  ", dict(tally))
