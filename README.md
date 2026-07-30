# UK Property Auction Intelligence — Data Pipeline

All data sources are free. No paid APIs.

## What each field comes from

| Field | Source | Cost |
|---|---|---|
| Guide/start price | Auction house results pages (SDL first) | Free (scrape) |
| Final sale (hammer) price | Auction house results pages | Free (scrape) |
| Sold / unsold / withdrawn | Auction house results pages | Free (scrape) |
| Days on market (auction cycle + re-offers) | Derived: listed_at → auction_date, re-offer tracking | Free (derived) |
| Condition | Keyword classifier over lot description text | Free (derived) |
| Floor area, property age, type, UPRN | EPC register API (epc.opendatacommunities.org) | Free (register email) |
| Prior sales of the same property | Land Registry Price Paid Data | Free (OGL) |
| Neighbourhood average for similar property | Land Registry PPD + UK HPI adjustment | Free (OGL) |

## Pipeline

```
1. SCRAPE     scrape_sdl.py     → auction house results → `lots` table
2. ENRICH     enrich.py         → EPC match (postcode + house number → UPRN, floor area, age)
                                → PPD match (prior sales of this property)
                                → condition classification (keywords)
                                → re-offer count (same property_key in earlier auctions)
3. COMPS      enrich.py         → postcode-sector comps, HPI-adjusted median
                                → discount % = hammer vs estimated market value
4. SERVE      Next.js/Supabase  → the tables above are designed for Supabase Postgres
```

## How the SDL scraper actually works

Verified against the live site on 2026-07-30. The obvious approach does not work,
so this is worth reading before adding another auction house:

- The event page (`/auction/{id}/{slug}/`) renders an **empty** lot container
  (`<div class="property-listings" id="searchView"></div>`). Parsing that HTML
  yields zero lots, and so does POSTing the visible search form to `/search`.
  The cards are injected client-side.
- The real source is a theme AJAX endpoint:
  `POST /wp-content/themes/sdl-auctions/library/property-functions.php`
  with `func=ajaxProp` and a urlencoded querystring in `data`.
- **`limit=All` returns every lot in one response** (224 for a typical event), so
  a full 33-event backfill is ~33 requests, not thousands.
- Event URLs carry the auction date in the slug
  (`/auction/1267/live-streamed-auction-2025-01-30/`), which is where
  `auction_date` comes from — no date parsing off the page needed.
- Lot **descriptions are not on the cards**. They are on each `/property/{id}/`
  page under `.entry-content`, i.e. one extra request per lot. Opt in with
  `--with-descriptions` (a single event is ~224 extra requests ≈ 11 min at the
  3s rate limit).

### Result vocabulary (this is not what you'd guess)

Taken from a live 224-lot event, with counts:

| Wording on the site | status | Count |
|---|---|---|
| `Sold at Auction £72,000` | `sold` | 55 |
| `Sold Prior to Auction` | `sold_prior` | 60 |
| `Sold After Auction` | `sold_after` | 2 |
| `Re-entry to a future auction` | `unsold` | 47 |
| `Withdrawn` / `Withdrawn Post` | `withdrawn` | 37 |
| `Postponed` | `postponed` | 23 |

Two consequences that matter for any analysis built on this:

1. **Only ~25% of lots publish a hammer price.** "Sold Prior to Auction" is
   another ~27% of lots and SDL publishes **no price** for those, so
   `hammer_price` is legitimately null on a sold lot. Any discount or sell-through
   metric has to say which denominator it is using.
2. SDL never uses the words "unsold", "not sold" or "available". Its term for
   *didn't sell* is **"Re-entry to a future auction"** — which is also the
   re-offer signal the README describes below.

## Setup

```bash
pip install requests beautifulsoup4 psycopg2-binary python-dotenv pytest
```

1. **EPC API key** (free): register at https://epc.opendatacommunities.org/ — you get
   Basic-auth credentials (your email + key). Put in `.env` as `EPC_EMAIL` / `EPC_KEY`.
2. **Land Registry PPD**: download the yearly CSV (or full ~5GB file) from
   https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads
   and load into the `ppd` table (loader in enrich.py). Updated monthly.
3. **UK HPI**: monthly CSV from gov.uk "UK House Price Index" — load into `hpi`.
   Set `HPI_AREA_CODE` in `.env` if you want a region other than UK-wide
   (`K02000001`); the table is keyed by `(area_code, month)` and a lookup by
   month alone would pick an arbitrary region.
4. Apply `schema.sql` to your Supabase project. **Needs Postgres 15+** for the
   `unique nulls not distinct` constraint.
5. Run `scrape_sdl.py` on a schedule. GitHub Actions cron is free and is the
   recommended runner (no server needed):
   ```yaml
   on:
     schedule:
       - cron: "0 6 * * *"
   ```

## Running it

```bash
python src/scrape_sdl.py --max-events 3 --out lots.jsonl
```

```bash
python src/scrape_sdl.py --auction-id 1267 --with-descriptions --out lots.jsonl
```

```bash
python src/enrich.py --lots lots.jsonl --no-db --no-epc
```

```bash
python src/enrich.py --load-ppd pp-2025.csv
```

```bash
python -m pytest
```

`--no-db` runs the condition classifier and prints JSON without touching Postgres —
useful before you have a `DATABASE_URL`.

## Days on market — how to interpret it for auctions

Auctions run a fixed cycle (catalogue → auction day, ~3–4 weeks), so classic DOM is
less meaningful than:
- **listed_at → auction_date** per listing (catalogue exposure time). SDL exposes
  the listing date as `data-date` on each card, so this is measured, not inferred.
- **re-offer count**: the same property appearing in multiple auctions (didn't sell,
  or sold prior). This is the strongest "distressed / stale" signal and the pipeline
  tracks it by normalised address (`property_key`) across auction events.

`property_key` is `houseno|postcode` and is only set when the address genuinely
starts with a house number (~73% of lots). Flats, named buildings and land parcels
get no key rather than a wrong one — matching "169" out of "Land between 169 and
177 Spital Lane" would create false re-offer matches.

## Scraping etiquette / legal

- `robots.txt` for sdlauctions.co.uk allows `/` for a generic user-agent, and none
  of the paths this scraper uses are disallowed. It **does** disallow a list of
  named AI crawlers (`ClaudeBot`, `GPTBot`, `CCBot`, `Google-Extended`, …) and sets
  `Content-Signal: search=yes, ai-train=no, use=reference`. Do not feed the scraped
  description text into model training, and re-check this file periodically — it is
  the site owner's stated position and it can change.
- Rate-limit (the scraper sleeps `DELAY_S` between requests), identify yourself with
  a real User-Agent + contact email, cache pages, and only hit public results pages.
- Results are facts (prices, addresses) but the description text and photos are the
  auction house's content — store descriptions for internal classification, be careful
  about republishing them verbatim on your site.
- Check `robots.txt` and terms for each new auction house before adding a scraper.

## Extending

Each auction house needs its own small scraper (Allsop, Bond Wolfe, Auction House UK,
Pugh all publish results). Keep the output shape identical to `LotRecord` in
scrape_sdl.py and everything downstream works unchanged. Shared address/price/status
parsing lives in `src/common.py` — reuse it so `property_key` stays consistent across
sources, otherwise re-offer tracking and PPD matching silently stop working.
