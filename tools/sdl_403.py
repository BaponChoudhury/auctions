"""Is SDL blocking us now, and has their robots.txt position changed?"""
import re, time
import requests

BASE = "https://www.sdlauctions.co.uk"
UA = "AuctionResearchBot/0.1 (contact: mailahb2017@gmail.com)"
H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
     "Accept-Language": "en-GB,en;q=0.9"}

print("=== robots.txt now ===")
r = requests.get(f"{BASE}/robots.txt", headers={"User-Agent": UA}, timeout=30)
print("status:", r.status_code)
txt = r.text if r.status_code == 200 else ""
print(txt[:700])

print("\n=== which endpoints still respond? ===")
checks = [
    ("results index", f"{BASE}/property-auctions/past-auctions/"),
    ("event page", f"{BASE}/auction/1267/live-streamed-auction-2025-01-30/"),
    ("lot detail", f"{BASE}/property/45665/terraced-house-for-auction-burton-on-trent/"),
]
for label, url in checks:
    try:
        resp = requests.get(url, headers=H, timeout=30)
        server = resp.headers.get("server", "")
        cf = resp.headers.get("cf-mitigated") or resp.headers.get("cf-ray", "")
        print(f"  {label:14} {resp.status_code}  {len(resp.text):7} bytes  "
              f"server={server} cf={cf[:20]}")
        if resp.status_code == 403:
            body = re.sub(r"<[^>]+>", " ", resp.text)
            body = re.sub(r"\s+", " ", body).strip()
            print(f"     body: {body[:220]}")
    except requests.RequestException as e:
        print(f"  {label:14} ERR {type(e).__name__}")
    time.sleep(3)

print("\n=== the AJAX results endpoint (what the scraper mainly uses) ===")
inner = ("location=&radius=3&minBeds=&maxBeds=&minPrice=&maxPrice="
         "&auctionId=1267&include%5B%5D=&lat=&lng=&bounds="
         "&tempType=auction&search=1&limit=All&page=1&order=Lot+Number&oos=0")
resp = requests.post(
    f"{BASE}/wp-content/themes/sdl-auctions/library/property-functions.php",
    data={"func": "ajaxProp", "data": inner},
    headers={**H, "X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/"},
    timeout=60)
print("  status:", resp.status_code, "len:", len(resp.text))
