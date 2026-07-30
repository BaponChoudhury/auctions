"""Dump one Bond Wolfe card's structure so selectors can be written from fact."""
import re
from bs4 import BeautifulSoup

soup = BeautifulSoup(open("bw_lots.html", encoding="utf-8").read(), "html.parser")
cards = soup.select(".Properties-cardWrap")
print("cards:", len(cards))

# Find a card that actually sold, so the price element is present.
sold = [c for c in cards if "sold" in c.get_text(" ").lower()]
print("cards mentioning sold:", len(sold))
c = sold[0] if sold else cards[0]

print("\n--- element inventory ---")
seen = {}
for e in c.find_all(True):
    cls = " ".join(e.get("class") or [])
    if not cls or cls in seen:
        continue
    txt = re.sub(r"\s+", " ", e.get_text(" ", strip=True))[:80]
    seen[cls] = True
    print(f"  {e.name:6} .{cls[:52]:54} {txt}")

print("\n--- links ---")
for a in c.select("a[href]")[:4]:
    print("  ", a["href"][:90])

print("\n--- raw (first 1600 chars) ---")
print(re.sub(r"\n\s*\n", "\n", c.prettify()[:1600]))
