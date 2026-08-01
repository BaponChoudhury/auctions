"""Sanity-check the EPC payload we just pulled, and size the full run."""
import json, statistics

cache = json.load(open("../data/epc_probe.json", encoding="utf-8"))
certs = [c for v in cache.values() for c in v]
print(f"postcodes: {len(cache)}  certificates: {len(certs)}  "
      f"avg {len(certs)/len(cache):.0f} per postcode")

areas = [c["floor_area_m2"] for c in certs if c["floor_area_m2"]]
print(f"floor areas: {len(areas)}  median {statistics.median(areas):.0f} m2  "
      f"range {min(areas):.0f}-{max(areas):.0f}")

print("\nsample certificates:")
for c in certs[:6]:
    print(f"  {str(c['house_no']):>5}  {str(c['floor_area_m2']):>7} m2  "
          f"{str(c['age_band'])[:22]:24} {str(c['built_form'])[:18]:20} "
          f"{c['address'][:38]}")

filled = {k: sum(1 for c in certs if c[k]) for k in
          ("floor_area_m2", "age_band", "built_form", "epc_property_type",
           "uprn", "house_no")}
print("\nfield coverage:")
for k, n in filled.items():
    print(f"  {k:20} {n:4}/{len(certs)}  ({100*n//len(certs)}%)")

print(f"\nCOST OF THE NAIVE APPROACH")
print(f"  ~{len(certs)/len(cache):.0f} certificate fetches per postcode")
print(f"  8,000 postcodes -> ~{8000*len(certs)/len(cache):,.0f} requests")
print(f"  at 20/s that is {8000*len(certs)/len(cache)/20/3600:.1f} hours")
print("  Only ONE certificate per lot is actually needed: the one whose house")
print("  number matches. Fetch that one and the run is ~16,000 requests.")
