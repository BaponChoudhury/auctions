# UK Property Auction Intelligence — Data Pipeline

All data sources are free. No paid APIs.

## What each field comes from

| Field | Source | Cost |
|---|---|---|
| Postcode, sector | Parsed from the lot address | Free (derived) |
| Town, local authority, region, lat/lng | postcodes.io (ONS data) | Free (OGL, no key) |
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

## Sources

Single-source data is not a robust basis for market conclusions, so the pipeline
is built around a shared `LotRecord` shape and one scraper per auction house.
Two are implemented; a test asserts both emit the identical record shape so the
schema and `enrich.py` never fork per source.

| Source | Scraper | Events | Lots | Guide | Hammer | Description |
|---|---|---|---|---|---|---|
| Bond Wolfe | `src/scrape_bondwolfe.py` | 51 | 9,219 | **no** | 71% | on the card |
| SDL Property Auctions | `src/scrape_sdl.py` | 32 | 5,360 | 99% | 28% | extra request per lot |
| Allsop | `src/scrape_allsop.py` | 10 | 1,814 | 98% | 53% | in the API response |

**Total: 16,393 lots, 93 auctions, £1.31bn of hammer prices, 55% priced.**

**The sources are not interchangeable, and the differences matter:**

- **Bond Wolfe publishes no guide price on past results.** Any "sold vs guide"
  figure can only be computed on SDL and Allsop data. Averaging all three on that
  metric produces a number that means nothing.
- **Hammer-price coverage ranges from 28% to 71%.** All three withhold the price
  on "sold prior/after" lots, but they differ hugely in how many lots sell that
  way. A naive sell-through comparison between houses measures their disclosure
  policy, not their markets.
- **Allsop is the richest source**: guide, sale price and per-lot feature bullets
  all arrive in one JSON response, so it is the only one that supports condition
  classification without an extra request per lot. It also runs commercial
  catalogues alongside residential.
- Bond Wolfe tags lots with condition/tenure badges ("Renovation", "Vacant",
  "Investment") kept verbatim in `result_raw` — a free cross-check on the keyword
  condition classifier.

Where they agree: postcode ~99%, `property_key` 70–83%, property type 88–98%.
Those are the fields comps and re-offer tracking depend on, so cross-source joins
are sound: 35 properties appear at more than one house, and 898 postcode sectors
are covered by more than one source.

### Candidate sources checked

`robots.txt` reviewed for eight UK auction houses on 2026-07-30. None blanket-block
a generic user-agent. Named AI-crawler blocks (`ClaudeBot`, `GPTBot`, …) exist on
SDL, Network Auctions and Savills (GPTBot only); Bond Wolfe, Allsop, Pugh and
Barnett Ross have none. Auction House UK and Clive Emson return 406 for
`robots.txt` and need a closer look before scraping. Re-check before adding any
source — `tools/probe_sources.py` does this.

## Recovering missing sale prices from Land Registry

Auction houses publish a price only for lots sold **at** auction — never for
"sold prior" or "sold after". That is ~45% of sold lots with no figure. But every
completed residential sale in England & Wales is registered, so the price can be
recovered by matching a lot to its PPD transaction on
**postcode + house number (PAON) + a completion date shortly after the auction**.

```bash
python tools/ppd_download.py 2019 2020 2021 2022 2023 2024 2025 2026
```

```bash
python src/ppd_match.py --lots "data/*.jsonl" --validate --out data/matched.jsonl
```

**It works, and it is measurably accurate.** Validated against the 5,288 lots
where the hammer price *is* published:

| | |
|---|---|
| Exact price match | **4,980 (94%)** |
| Within £1,000 | 5,030 (95%) |
| Median difference | **£0** |
| Completion lag after auction | median 29 days (p10 22, p90 56) |

Result on the current corpus: **6,652 lots matched, 811 new auction prices
recovered** where none was published, plus 553 later private sales of lots that
did *not* sell at auction.

### The window was chosen from evidence, not assumption

`tools/ppd_sweep.py` scores each window against the known hammer prices:

| Window | Matched | Exact |
|---|---|---|
| −30 to +120 days | 2,395 | 78% |
| 0 to +120 days | 2,272 | **92%** |
| 0 to +90 days | 2,227 | 93% |
| 0 to +45 days | 1,846 | 97% |

A pre-auction window is almost pure false positives: it matches **the previous
owner's purchase**, which skewed matched prices low by a median of £10,000.
Default is now `0..+90`.

### Limits, all measured rather than assumed

- **Registration lag is the dominant limit.** PPD currently reaches 2026-06-30
  and the last month or two is always partial. Match rate on sold lots by auction
  month: 62% (Jul 2025) → 25% (Jan 2026) → 3% (May 2026) → **0% (Jun–Jul 2026)**.
  This is why Allsop matches at only 14% — all ten of its auctions are 2026.
  **PPD backfills history; it cannot price a recent auction.**
- **Residential only.** Commercial lots never appear: 22% match for land/commercial
  versus 73% for Bond Wolfe residential.
- **England & Wales only.** Scottish lots can never match.
- **Needs a house number.** Named buildings and land parcels have no PAON number.
  Flats often need a SAON the matcher does not yet use — Allsop flats match at 4%.
- A match on a lot that did **not** sell at auction is a later private sale, not
  an auction result. Those are labelled `recovered_kind = "later_sale"` and must
  never be read as a hammer price.
- 178 matches had more than one candidate sale in the window; they are flagged
  `recovered_ambiguous`.

## Geography

The scrapers record a **postcode** (99% coverage) and derive a **postcode sector**,
but no town, region or local authority — those only existed inside the raw address
string. `src/geo.py` resolves postcode → area via postcodes.io (free, OGL, no key,
100 per request) and caches to disk, since postcode→area never changes.

```bash
python src/geo.py --lots data/sdl_all.jsonl data/bw_all.jsonl --to-db
```

Current corpus: **10,787 of 10,827 postcodes resolved (99%), across 336 local
authorities.**

This is not cosmetic. `hpi` is keyed by `(area_code, month)` where `area_code` is
an ONS code, and `postcode_geo.admin_district_code` is exactly that code. Before
this, every comp in the corpus was time-adjusted by one national index. The corpus
median sale runs from **£45,000 in the North East to £293,000 in London — a 6.5×
spread**, so a single national ratio was never going to be right. `enrich.py` now
resolves each lot's local-authority series and falls back to national only when the
postcode cannot be resolved. Setting `HPI_AREA_CODE` forces every lot back onto one
series and says so on stderr.

Area lives in `postcode_geo` rather than as columns on `lots`: it is postcode-level
fact, and ~7k lots share ~4.8k postcodes. Join through the `lots_geo` view.

| Region | Sold lots | Median sale |
|---|---|---|
| West Midlands | 5,225 | £129,500 |
| East Midlands | 1,303 | £110,000 |
| North West | 631 | £70,000 |
| North East | 596 | £32,500 |
| Yorkshire & Humber | 417 | £57,500 |
| London | 257 | £321,000 |
| South East | 178 | £192,250 |
| East of England | 137 | £172,000 |
| South West | 104 | £150,000 |

**Median sale spans £32,500 (North East) to £321,000 (London) — a 9.9× spread.**
That is the whole argument for per-area HPI adjustment rather than one national index.

The sample is still Midlands-weighted: SDL and Bond Wolfe are both Midlands-based,
and adding Allsop took London from 20 sold lots to 257 without changing that overall
shape. Treat national conclusions from this corpus with suspicion until a
southern-focused house (Clive Emson, Barnett Ross) is added.

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
python src/scrape_sdl.py --max-events 0 --out lots.jsonl
```

```bash
python src/scrape_bondwolfe.py --max-events 0 --out bondwolfe.jsonl
```

```bash
python src/scrape_allsop.py --max-events 0 --out allsop.jsonl
```

```bash
python tools/combine.py data/lots.jsonl data/bondwolfe.jsonl
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

Each auction house needs its own small scraper. Keep the output shape identical to
`LotRecord` in scrape_sdl.py and everything downstream works unchanged — there is a
test asserting this. Shared address/price/status parsing lives in `src/common.py` —
reuse it so `property_key` stays consistent across sources, otherwise re-offer
tracking and PPD matching silently stop working.

Both scrapers so far hit the same wall: the visible listing is rendered
client-side and returns zero lots to a plain HTML parse. In both cases the data
came from an admin-ajax-style endpoint found by reading the theme's own JS.
Expect the next source to be the same, and budget for it.

Allsop was the exception — a clean JSON API behind a React SPA, found by reading
the bundle. Check for one before writing HTML parsing.

Traps worth knowing before writing a fourth scraper, all of which bit here:

1. **A status word can live somewhere other than the status element.** Bond Wolfe
   unsold lots carry no status tag at all — the word only appears in the price
   block — so reading the obvious element filed all of them as `listed`.
2. **`"unsold"` contains `"sold"`.** A substring test in the wrong order files
   every unsold lot as a sale. Test `unsold` first, or use word boundaries.
3. **Epoch timestamps may be local midnight, not UTC.** Allsop's `auction_date`
   is UK-local midnight in epoch ms; read back as UTC it is 23:00 the previous
   day during BST, so every summer auction landed one day early. Caught by
   diffing against the dates Allsop publishes on its own index — winter events
   agreed, every BST event was off by one. A wrong `auction_date` corrupts the
   `lots` unique key.
4. **A generic type label can hide the real one.** Allsop's residential catalogue
   labels most lots a bare `"House"`; the built form is only in the byline. 133 of
   301 lots in one auction had no usable type until that fallback was added.

`tests/test_parsing.py` pins all four.

Always score a new source's status vocabulary against a real event before trusting
it — `tools/check_source.py` prints the distribution and field coverage.
