"""Are the named bots on these portals allowed or disallowed?"""
import re
import requests

UA = "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"
for name, base in (("Rightmove", "https://www.rightmove.co.uk"),
                   ("OnTheMarket", "https://www.onthemarket.com")):
    txt = requests.get(f"{base}/robots.txt", headers={"User-Agent": UA},
                       timeout=30).text
    print(f"\n=== {name}: rules for named agents ===")
    blocks = re.split(r"(?im)^user-agent:\s*", txt)
    for b in blocks[1:]:
        agent = b.splitlines()[0].strip()
        if agent == "*":
            continue
        rules = [l.strip() for l in b.splitlines()[1:]
                 if l.strip().lower().startswith(("allow:", "disallow:"))]
        verdict = "BLOCKED entirely" if any(
            r.lower().replace(" ", "") == "disallow:/" for r in rules) else \
            ("allowed" if rules else "no rules")
        print(f"  {agent:22} {verdict:18} {rules[:2]}")

# Zoopla refuses robots.txt to this UA - record exactly what it returns.
r = requests.get("https://www.zoopla.co.uk/robots.txt",
                 headers={"User-Agent": UA}, timeout=30)
body = re.sub(r"<[^>]+>", " ", r.text)
print(f"\n=== Zoopla robots.txt -> {r.status_code} ===")
print("  ", re.sub(r"\s+", " ", body).strip()[:200])
print("   cf-mitigated:", r.headers.get("cf-mitigated"),
      "| server:", r.headers.get("server"))
