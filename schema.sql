-- UK Auction Intelligence — Supabase/Postgres schema
-- Requires Postgres 15+ (for `nulls not distinct`). Supabase is 15+.

-- One row per lot appearance in an auction. The same physical property
-- re-offered later = a new row, linked via property_key.
create table if not exists lots (
  id            bigint generated always as identity primary key,
  source        text not null,                -- 'sdl', 'allsop', ...
  source_lot_id text,                         -- lot id on the source site (SDL: data-id)
  lot_url       text,
  auction_date  date,
  first_seen    date not null default current_date,
  listed_at     date,                         -- when the lot was published (SDL: data-date)
  address_raw   text not null,
  postcode      text,                         -- normalised, e.g. 'ST16 2AB'
  postcode_sector text,                       -- 'ST16 2' (comps grouping key)
  property_key  text,                         -- normalised 'houseno|postcode' for re-offer tracking
  guide_price   integer,                      -- £; guide as published (lower bound if a range)
  guide_price_max integer,                    -- £; upper bound when the guide is a range
  hammer_price  integer,                      -- £; null if unsold OR sold prior (no price published)
  status        text,                         -- see vocabulary note below
  result_raw    text,                         -- verbatim result wording from the source
  description   text,
  property_type text,                         -- 'D','S','T','F','O' (PPD convention) if inferable
  bedrooms      integer,
  scraped_at    timestamptz default now(),
  -- auction_date is nullable, and the Postgres default (NULLS DISTINCT) would let
  -- the same lot insert repeatedly whenever the date is unknown. Treat nulls as equal.
  constraint lots_source_lot_uniq unique nulls not distinct (source, source_lot_id, auction_date)
);
create index if not exists lots_sector_idx       on lots (postcode_sector);
create index if not exists lots_property_key_idx on lots (property_key);
create index if not exists lots_auction_date_idx on lots (auction_date);

-- Status vocabulary, taken from live SDL result wording rather than assumed:
--   'sold'        — 'Sold at Auction £X' (hammer_price set)
--   'sold_prior'  — 'Sold Prior to Auction' (NO price published: ~27% of lots)
--   'sold_after'  — 'Sold After Auction'
--   'unsold'      — 'Re-entry to a future auction'  (SDL's wording for "did not sell")
--   'withdrawn'   — 'Withdrawn' / 'Withdrawn Post'
--   'postponed'   — 'Postponed'
--   'listed'      — no result yet (auction not run, or results not published)
alter table lots drop constraint if exists lots_status_chk;
alter table lots add constraint lots_status_chk check (status in (
  'sold','sold_prior','sold_after','unsold','withdrawn','postponed','listed'
));

-- EPC enrichment, one row per lot (best match)
create table if not exists lot_epc (
  lot_id        bigint primary key references lots(id) on delete cascade,
  uprn          text,
  floor_area_m2 numeric,
  construction_age_band text,
  epc_rating    text,
  epc_property_type text,
  match_confidence text                       -- 'exact' | 'fuzzy' | 'none'
);

-- Land Registry Price Paid Data (loaded from the official CSV)
create table if not exists ppd (
  transaction_id text primary key,
  price          integer not null,
  transfer_date  date not null,
  postcode       text,
  property_type  text,                        -- D/S/T/F/O
  new_build      boolean,
  tenure         text,                        -- F/L
  paon           text,                        -- house number/name
  saon           text,                        -- flat/unit
  street         text,
  town           text
);
create index if not exists ppd_postcode_idx on ppd (postcode);
-- prior_sales() filters on lower(paon); without this the postcode index still
-- forces a scan of every sale in that postcode.
create index if not exists ppd_postcode_paon_idx on ppd (postcode, lower(paon));
-- sector_comps() filters on `postcode like 'ST16 2%'`; text_pattern_ops is what
-- makes that prefix match indexable.
create index if not exists ppd_postcode_prefix_idx on ppd (postcode text_pattern_ops);
create index if not exists ppd_type_date_idx on ppd (property_type, transfer_date);

-- Postcode -> area reference data (postcodes.io, OGL). Keyed by postcode rather
-- than by lot: it is postcode-level fact, it never changes, and ~7k lots share
-- ~6k postcodes, so this is looked up once and reused forever.
--
-- admin_district_code is the ONS code (e.g. E08000025 Birmingham) and is what
-- joins to hpi.area_code — without it every comp in the corpus is time-adjusted
-- by a single national index regardless of where the property is.
create table if not exists postcode_geo (
  postcode                   text primary key,
  admin_district             text,      -- local authority, e.g. 'Birmingham'
  admin_district_code        text,      -- ONS code, joins to hpi.area_code
  admin_county               text,
  admin_county_code          text,
  admin_ward                 text,
  region                     text,      -- e.g. 'West Midlands', 'London'
  country                    text,
  parliamentary_constituency text,
  lsoa                       text,
  latitude                   numeric,
  longitude                  numeric
);
create index if not exists postcode_geo_district_idx on postcode_geo (admin_district_code);
create index if not exists postcode_geo_region_idx   on postcode_geo (region);

-- Lots carry a postcode, so area comes from a join rather than a duplicated column.
create or replace view lots_geo as
  select l.*, g.admin_district, g.admin_district_code, g.region, g.admin_county,
         g.latitude, g.longitude
  from lots l left join postcode_geo g on g.postcode = l.postcode;

-- UK House Price Index (monthly, by local authority) for time-adjusting comps.
-- NOTE: rows exist per area_code, so any lookup by month alone must also pin an
-- area_code or it picks an arbitrary region's index.
create table if not exists hpi (
  area_code   text,
  region_name text,
  month       date,
  index_value numeric,
  avg_price   numeric,
  primary key (area_code, month)
);

-- Computed results, one row per lot
create table if not exists lot_analysis (
  lot_id             bigint primary key references lots(id) on delete cascade,
  condition_class    text,      -- 'ready' | 'light_refurb' | 'full_refurb' | 'structural' | 'unknown'
  condition_flags    text[],    -- e.g. {'tenanted','hmo'}
  prior_sale_price   integer,   -- last PPD sale of this exact property
  prior_sale_date    date,
  comp_count         integer,
  comp_median_price  integer,   -- HPI-adjusted median of neighbourhood comps
  discount_pct       numeric,   -- (comp_median - hammer) / comp_median * 100
  reoffer_count      integer,   -- times this property_key was seen in earlier auctions
  computed_at        timestamptz default now()
);
