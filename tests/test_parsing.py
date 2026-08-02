"""Network-free tests for the parsing and classification logic.

The status/guide/address strings below are verbatim from a live SDL event page
(auction 1267, 30 Jan 2025, 224 lots), not invented.
"""

import pytest

from common import (
    classify_status,
    house_number,
    make_keys,
    parse_postcode,
    parse_price,
    parse_price_range,
    property_type_code,
)
from enrich import classify_condition
from scrape_bondwolfe import (
    classify_status as bw_status,
    parse_auction_date,
    parse_type,
)
from geo import _shape as geo_shape, lookup as geo_lookup
from ppd_match import candidates, paon_number
from epc_load import match as epc_match
from scrape_emson import (
    classify_status as emson_status,
    parse_price as emson_price,
    property_type as emson_type,
)
from scrape_allsop import (
    auction_date as allsop_date,
    classify_status as allsop_status,
    description as allsop_desc,
    property_type as allsop_type,
)


# ------------------------------------------------------------------ status ---
@pytest.mark.parametrize("text,status,hammer", [
    ("Sold at Auction £72,000",           "sold",       72000),
    ("Sold at Auction £172,500",          "sold",       172500),
    ("Sold Prior to Auction",             "sold_prior", None),
    ("Sold After Auction",                "sold_after", None),
    ("Re-entry to a future auction",      "unsold",     None),
    ("Re-entry to a future auction £X",   "unsold",     None),
    ("Withdrawn",                         "withdrawn",  None),
    ("Withdrawn Post",                    "withdrawn",  None),
    ("Postponed",                         "postponed",  None),
    ("\xa0",                              "listed",     None),
    ("",                                  "listed",     None),
])
def test_classify_status(text, status, hammer):
    assert classify_status(text) == (status, hammer)


def test_withdrawn_price_is_not_a_hammer_price():
    """'Withdrawn £95,000' appears in the data; that figure is not a sale."""
    status, hammer = classify_status("Withdrawn £95,000")
    assert status == "withdrawn"
    assert hammer is None


def test_reentry_is_unsold_not_listed():
    """The original classifier looked for 'unsold'/'not sold'/'available', none of
    which SDL ever uses — every one of the 47 re-entry lots fell through to
    'listed', silently hiding the strongest distressed signal in the dataset."""
    assert classify_status("Re-entry to a future auction")[0] == "unsold"


# ------------------------------------------------------------------- price ---
@pytest.mark.parametrize("text,lo,hi", [
    ("£175,000+ (plus fees)",           175000, None),
    ("£95,000 + (plus fees)",           95000,  None),
    ("£700,000 - £750,000 (plus fees)", 700000, 750000),
    ("£125,000 (plus fees)",            125000, None),
    ("no price here",                   None,   None),
])
def test_parse_price_range(text, lo, hi):
    assert parse_price_range(text) == (lo, hi)


def test_parse_price_takes_first_amount():
    assert parse_price("Sold at Auction £72,000") == 72000


# ----------------------------------------------------------------- address ---
@pytest.mark.parametrize("addr,postcode", [
    ("9 Byrkley Street, Burton-On-Trent DE14 2EG", "DE14 2EG"),
    ("7 Reuben Street, Stockport, Greater Manchester SK4 1PS", "SK4 1PS"),
    ("Flat 4, Witley House, Redlands Way, London, Greater London SW2 3LR", "SW2 3LR"),
    ("Somewhere with no postcode", None),
])
def test_parse_postcode(addr, postcode):
    assert parse_postcode(addr) == postcode


@pytest.mark.parametrize("addr,expected", [
    ("9 Byrkley Street, Burton-On-Trent DE14 2EG", "9"),
    ("21 & 21A Victory Road, Derby DE24 8EJ", "21"),
    ("87 London Road, Coalville", "87"),
    # Anchored on purpose — an unanchored \d+ would return "169" here and invent
    # a property_key for a parcel of land that has no house number.
    ("Land between 169 and 177 Spital Lane, Chesterfield S41 0HL", None),
    ("The Old Butchers Shop, Main Street, Winster", None),
])
def test_house_number(addr, expected):
    assert house_number(addr) == expected


def test_make_keys():
    sector, key = make_keys("9 Byrkley Street, Burton-On-Trent DE14 2EG", "DE14 2EG")
    assert sector == "DE14 2"
    assert key == "9|DE14 2EG"


def test_make_keys_without_house_number_yields_no_property_key():
    sector, key = make_keys("Land between 169 and 177 Spital Lane", "S41 0HL")
    assert sector == "S41 0"
    assert key is None


# ------------------------------------------------------------ property type ---
@pytest.mark.parametrize("title,code", [
    ("Terraced House in Burton-On-Trent",   "T"),
    ("End of Terrace House in Winster",     "T"),
    ("Semi-detached House in Derby",        "S"),
    ("Detached House in Cannock",           "D"),
    ("Flat in London",                      "F"),
    ("Studio Flat in Leeds",                "F"),
    ("Land in Chesterfield",                "O"),
    ("Commercial Property in Mold",         "O"),
    ("House of Multiple Occupation in Hull", "O"),
    # Deliberately unmapped: a bungalow's PPD built-form is ambiguous, and
    # guessing would compare it against the wrong comp set.
    ("Bungalow in Rhyl",                    None),
    ("Cottage in Matlock",                  None),
])
def test_property_type_code(title, code):
    assert property_type_code(title) == code


# ------------------------------------------------------------------ condition ---
@pytest.mark.parametrize("desc,cls", [
    ("The property requires modernisation throughout", "full_refurb"),
    ("Evidence of structural movement to the rear",    "structural"),
    ("Would benefit from some cosmetic updating",      "light_refurb"),
    ("A well presented home, ready to let",            "ready"),
    ("A classic two double bedroom home",              "unknown"),
])
def test_classify_condition_class(desc, cls):
    assert classify_condition(desc)[0] == cls


def test_worst_condition_class_wins():
    """Rule order matters: a description mentioning both must classify as the worse."""
    desc = "Well presented but with evidence of subsidence to the rear elevation"
    assert classify_condition(desc)[0] == "structural"


def test_condition_flags():
    flags = classify_condition("Sold subject to tenancy. HMO licence in place.")[1]
    assert set(flags) >= {"tenanted", "hmo"}


def test_classify_condition_handles_missing_description():
    assert classify_condition("") == ("unknown", [])
    assert classify_condition(None) == ("unknown", [])


# --- real listing copy that the original substring ruleset scored as 'unknown' ---
@pytest.mark.parametrize("desc,cls", [
    ("The property requires general modernisation throughout but will make a fine home",
     "full_refurb"),
    ("A large terraced Villa in need of full modernisation and upgrading",
     "full_refurb"),
    ("A three bedroom, semi-detached property in Huddersfield. Requiring refurbishment.",
     "full_refurb"),
    ("a period property with attic room, which is in need of a scheme of updating and modernisation",
     "full_refurb"),
    ("mid-terraced property, requiring a scheme of improvement and upgrading",
     "full_refurb"),
    ("The property is in need of general modernisation throughout",
     "full_refurb"),
    ("the apartment is now in need of improvement throughout",
     "full_refurb"),
    ("accommodation requiring some modernisation and briefly comprising",
     "light_refurb"),
    ("a mid-terraced cottage in need of cosmetic improvement",
     "light_refurb"),
    ("the property would benefit from some modernisation",
     "light_refurb"),
    ("This property which is in exceptional condition is located within Nottingham",
     "ready"),
])
def test_real_listing_copy(desc, cls):
    assert classify_condition(desc)[0] == cls


def test_nearby_landmark_does_not_mark_a_lot_as_ready():
    """Auction copy sells the neighbourhood too. This exact sentence marked a lot
    as ready-to-occupy when the refurbished thing was a spa down the road."""
    desc = ("The property is located in the heart of Buxton town centre close to "
            "the newly refurbished Buxton Crescent Spa, Buxton Opera House")
    assert classify_condition(desc)[0] != "ready"


def test_derelict_outbuilding_is_not_a_structural_lot():
    """'part derelict brick coal stores' graded a whole house as structural."""
    desc = ("Initial garden area with patio, timber shed and part derelict brick "
            "coal stores. There is the potential to extend.")
    assert classify_condition(desc)[0] != "structural"


@pytest.mark.parametrize("heading,cls", [
    # Auction headings drop the verb: "<property> FOR <work>".
    ("MID-TERRACE HOUSE FOR REFURBISHMENT",              "full_refurb"),
    ("SEMI-DETACHED HOUSE FOR IMPROVEMENT",              "full_refurb"),
    ("FIVE-BEDROOM HOUSE FOR TOTAL REFURBISHMENT",       "full_refurb"),
    ("DETACHED BUNGALOW FOR IMPROVEMENT",                "full_refurb"),
    ("THREE-BEDROOM HOUSE IN NEED OF IMPROVEMENT",       "full_refurb"),
    ("GROUND FLOOR FLAT FOR IMPROVEMENT",                "full_refurb"),
])
def test_auction_heading_idiom(heading, cls):
    assert classify_condition(heading)[0] == cls


@pytest.mark.parametrize("heading", [
    "FREEHOLD LAND WITH POTENTIAL",
    "APPROXIMATELY 22 ACRES OF LAND WITH FUTURE POTENTIAL",
    "SUBSTANTIAL FREEHOLD 22-BEDROOM FORMER CARE HOME WITH POTENTIAL",
    "FORMER HOTEL FOR DEVELOPMENT POTENTIAL",
    "MODERN FREEHOLD TWO-BEDROOM TERRACE HOUSE FOR INVESTMENT",
    "DETACHED FOUR BEDROOM HOUSE - RESIDENTIAL INVESTMENT",
])
def test_potential_and_investment_are_not_condition(heading):
    """'WITH POTENTIAL' is development potential, not disrepair — it appears on
    land, former churches and care homes. 'FOR INVESTMENT' is a tenure signal.
    Reading either as 'needs refurbishment' would mislabel hundreds of lots."""
    assert classify_condition(heading)[0] == "unknown"


def test_genuine_structural_still_fires():
    assert classify_condition("Evidence of subsidence to the main elevation")[0] == "structural"


# ------------------------------------------------------- second source: Bond Wolfe ---
@pytest.mark.parametrize("tag,price,status,hammer", [
    ("Sold",      "Sold for £57,000",  "sold",       57000),
    ("Sold",      "Sold for £458,000", "sold",       458000),
    ("Withdrawn", "Withdrawn",         "withdrawn",  None),
    ("Postponed", "Postponed",         "postponed",  None),
    # Real Bond Wolfe string: a genuine sale that publishes no figure.
    ("", "Sold prior to auction, for an undisclosed amount", "sold_prior", None),
    # Unsold lots carry NO status tag — the word appears only in the price block.
    ("", "Unsold Auction: 9th Jul 2026", "unsold", None),
])
def test_bondwolfe_status(tag, price, status, hammer):
    assert bw_status(tag, price) == (status, hammer)


def test_unsold_is_not_read_as_sold():
    """'unsold' contains 'sold'. A substring test in the wrong order files every
    unsold lot as a sale — it briefly turned 16 unsold lots into sales here."""
    assert bw_status("", "Unsold")[0] == "unsold"
    assert classify_status("Unsold")[0] == "unsold"
    assert classify_status("Re-entry to a future auction")[0] == "unsold"


def test_undisclosed_prior_sale_has_no_price():
    """A figure is only trusted when attached to 'sold for'."""
    _, hammer = bw_status("", "Sold prior to auction, for an undisclosed amount")
    assert hammer is None


@pytest.mark.parametrize("tagline,code,beds", [
    ("3 bedroom mid terraced house in Stoke on Trent", "T", 3),
    ("4 bedroom semi-detached house in Solihull",      "S", 4),
    ("2 bedroom detached bungalow in Handsworth",      "D", 2),
    ("1 bedroom flat in Birmingham",                   "F", 1),
    ("Commercial property in Walsall",                 "O", None),
])
def test_bondwolfe_tagline(tagline, code, beds):
    assert parse_type(tagline) == (code, beds)


@pytest.mark.parametrize("text,iso", [
    ("Auction: 9th Jul 2026",  "2026-07-09"),
    ("Auction: 1st Feb 2025",  "2025-02-01"),
    ("Auction: 23rd Oct 2024", "2024-10-23"),
    ("no date here",           None),
])
def test_bondwolfe_auction_date(text, iso):
    assert parse_auction_date(text) == iso


# ------------------------------------------------------------------- geography ---
def _pio(**over):
    """A postcodes.io result, shaped like the real API response."""
    base = {"admin_district": "Birmingham", "admin_county": None,
            "admin_ward": "Handsworth Wood", "region": "West Midlands",
            "country": "England", "parliamentary_constituency": "Birmingham Perry Barr",
            "lsoa": "Birmingham 032D", "latitude": 52.516163, "longitude": -1.936939,
            "codes": {"admin_district": "E08000025", "admin_county": "E99999999"}}
    base.update(over)
    return base


def test_geo_keeps_the_ons_code_that_joins_to_hpi():
    g = geo_shape(_pio())
    assert g["admin_district_code"] == "E08000025"
    assert g["admin_district"] == "Birmingham"
    assert g["region"] == "West Midlands"


def test_geo_drops_the_not_applicable_county_sentinel():
    """postcodes.io returns E99999999 for 'no county', which is not an area code
    and would silently become a bogus hpi.area_code join key."""
    assert geo_shape(_pio())["admin_county_code"] is None


def test_geo_keeps_a_real_county_code():
    g = geo_shape(_pio(admin_county="Staffordshire",
                       codes={"admin_district": "E07000193",
                              "admin_county": "E10000028"}))
    assert g["admin_county_code"] == "E10000028"


def test_geo_shape_has_every_column_the_upsert_writes():
    g = geo_shape(_pio())
    for col in ("admin_district", "admin_district_code", "admin_county",
                "admin_county_code", "admin_ward", "region", "country",
                "parliamentary_constituency", "lsoa", "latitude", "longitude"):
        assert col in g, col


def test_lookup_uses_cache_and_makes_no_request():
    """A cached postcode must not hit the network — the corpus is ~6k postcodes
    and area data never changes."""
    cache = {"B20 2JH": geo_shape(_pio())}

    class Boom:
        def post(self, *a, **k):
            raise AssertionError("network call for an already-cached postcode")

    out = geo_lookup(["B20 2JH"], cache=cache, session=Boom(), verbose=False)
    assert out["B20 2JH"]["admin_district_code"] == "E08000025"


# --------------------------------------------------- Land Registry PPD matching ---
@pytest.mark.parametrize("paon,number", [
    ("44", "44"),
    # PPD's PAON is not always a bare number.
    ("LIME COURT, 114", "114"),
    ("21A", "21a"),
    ("THE OLD RECTORY", None),
    ("", None),
])
def test_paon_number(paon, number):
    assert paon_number(paon) == number


def _sale(price, d, paon="12"):
    return {"price": price, "date": d, "paon": paon,
            "paon_no": paon_number(paon), "saon": "", "type": "T"}


LOT = {"postcode": "DE14 2EG", "address_raw": "12 Byrkley Street, Burton DE14 2EG",
       "auction_date": "2025-01-30"}


def test_ppd_match_finds_the_completion_after_the_auction():
    idx = {"DE14 2EG": [_sale(72000, "2025-02-27")]}
    hits = candidates(LOT, idx, before=0, after=90)
    assert len(hits) == 1
    assert hits[0]["price"] == 72000
    assert hits[0]["lag_days"] == 28


def test_ppd_match_excludes_the_previous_owners_purchase():
    """A sale completing BEFORE the auction is the previous owner buying, not
    the auction result. Allowing a 30-day pre-window dropped exact price
    agreement from 92% to 78% and skewed matches low by a median of £10,000."""
    idx = {"DE14 2EG": [_sale(45000, "2025-01-02")]}
    assert candidates(LOT, idx, before=0, after=90) == []


def test_ppd_match_excludes_a_different_house_in_the_same_postcode():
    idx = {"DE14 2EG": [_sale(72000, "2025-02-27", paon="14")]}
    assert candidates(LOT, idx, before=0, after=90) == []


def test_ppd_match_excludes_sales_beyond_the_window():
    idx = {"DE14 2EG": [_sale(72000, "2025-08-30")]}
    assert candidates(LOT, idx, before=0, after=90) == []


def test_ppd_match_prefers_the_closest_completion():
    idx = {"DE14 2EG": [_sale(90000, "2025-04-20"), _sale(72000, "2025-02-27")]}
    hits = candidates(LOT, idx, before=0, after=90)
    assert len(hits) == 2 and hits[0]["price"] == 72000


def test_ppd_match_needs_a_house_number():
    """Named buildings and land parcels have no PAON number to match on, and
    guessing one would attach a stranger's sale price to the lot."""
    lot = {**LOT, "address_raw": "The Old Butchers Shop, Main Street"}
    assert candidates(lot, {"DE14 2EG": [_sale(72000, "2025-02-27")]}, 0, 90) == []


def test_ppd_match_needs_an_auction_date():
    lot = {**LOT, "auction_date": None}
    assert candidates(lot, {"DE14 2EG": [_sale(72000, "2025-02-27")]}, 0, 90) == []


# ----------------------------------------------- fourth source: Clive Emson ---
@pytest.mark.parametrize("raw,status", [
    ("Sold",            "sold"),
    ("Sold Prior",      "sold_prior"),
    ("Sold After",      "sold_after"),
    ("Withdrawn After", "withdrawn"),
    ("UNSOLD",          "unsold"),
    ("Postponed",       "postponed"),
    # Their wording for a lot rolled into the next sale.
    ("AVAILABLE IN OUR SEPTEMBER AUCTION", "unsold"),
    ("AVAILABLE IN OUR MAY AUCTION",       "unsold"),
])
def test_emson_status(raw, status):
    assert emson_status(raw) == status


def test_emson_unsold_not_swallowed_by_sold():
    """Third source, same substring trap: 'UNSOLD' must not match 'Sold'."""
    assert emson_status("UNSOLD") == "unsold"


def test_emson_withdrawn_after_is_not_a_sale():
    """'Withdrawn After' contains 'After'; it must not become sold_after."""
    assert emson_status("Withdrawn After") == "withdrawn"


@pytest.mark.parametrize("raw,price", [
    ("275,000", 275000),
    ("98,000", 98000),
    ("", None),
    (None, None),
])
def test_emson_price(raw, price):
    assert emson_price(raw) == price


@pytest.mark.parametrize("heading,code", [
    ("NEARLY 27 ACRES OF WOODLAND",                "O"),
    ("FREEHOLD GROUND RENTS",                      "O"),
    ("ELEVEN GARAGES WITH LAND IN RESIDENTIAL AREA", "O"),
    ("MID-TERRACE HOUSE FOR IMPROVEMENT",          "T"),
    ("SEMI-DETACHED HOUSE",                        "S"),
    ("GROUND FLOOR FLAT",                          "F"),
    # A house with no stated built form: guessing would poison the comp set.
    ("FOUR-BEDROOM HOUSE FOR IMPROVEMENT",         None),
])
def test_emson_property_type(heading, code):
    assert emson_type(heading) == code


# ------------------------------------------------------------- EPC matching ---
def _cert(addr, area=85.0, lodged="2024-01-01"):
    from common import house_number as hn
    return {"address": addr, "house_no": hn(addr), "floor_area_m2": area,
            "age_band": "1900-1929", "rating": "D", "epc_property_type": "House",
            "built_form": "Mid-Terrace", "uprn": "100", "lodged": lodged}


EPC_LOT = {"postcode": "DE14 2EG",
           "address_raw": "9 Byrkley Street, Burton-On-Trent DE14 2EG"}


def test_epc_matches_on_house_number():
    idx = {"DE14 2EG": [_cert("9 Byrkley Street"), _cert("11 Byrkley Street", 92.0)]}
    m = epc_match(EPC_LOT, idx)
    assert m["epc_match"] == "exact" and m["floor_area_m2"] == 85.0


def test_epc_prefers_the_most_recent_certificate():
    idx = {"DE14 2EG": [_cert("9 Byrkley Street", 80.0, "2012-05-01"),
                        _cert("9 Byrkley Street", 88.0, "2023-09-01")]}
    assert epc_match(EPC_LOT, idx)["floor_area_m2"] == 88.0


def test_epc_will_not_guess_between_several_certificates():
    """Attaching a neighbour's floor area would corrupt every £/m2 derived from it."""
    lot = {"postcode": "DE14 2EG", "address_raw": "The Old Rectory, Burton DE14 2EG"}
    idx = {"DE14 2EG": [_cert("9 Byrkley Street"), _cert("11 Byrkley Street")]}
    assert epc_match(lot, idx) is None


def test_epc_lone_certificate_is_flagged_fuzzy_not_exact():
    lot = {"postcode": "DE14 2EG", "address_raw": "The Old Rectory, Burton DE14 2EG"}
    idx = {"DE14 2EG": [_cert("9 Byrkley Street")]}
    assert epc_match(lot, idx)["epc_match"] == "fuzzy"


def test_epc_unknown_postcode_returns_nothing():
    assert epc_match(EPC_LOT, {}) is None


def test_all_sources_emit_the_same_record_shape():
    """enrich.py and the schema depend on this staying true as sources are added."""
    import dataclasses
    from scrape_sdl import LotRecord
    import scrape_bondwolfe, scrape_allsop, scrape_emson
    assert scrape_bondwolfe.LotRecord is LotRecord
    assert scrape_allsop.LotRecord is LotRecord
    assert scrape_emson.LotRecord is LotRecord
    fields = {f.name for f in dataclasses.fields(LotRecord)}
    assert {"source", "source_lot_id", "address_raw", "postcode", "property_key",
            "guide_price", "hammer_price", "status", "property_type"} <= fields


# ------------------------------------------------------------ third source: Allsop ---
@pytest.mark.parametrize("raw,price,status,hammer", [
    ("Sold",        "235000.00", "sold",       235000),
    ("Sold",        "1450000.00", "sold",      1450000),
    # Allsop publishes sale_price ONLY for lots sold at auction; prior/after
    # sales carry no figure at all (verified: 21/21 Sold, 0/17 Sold Prior).
    ("Sold Prior",  None,        "sold_prior", None),
    ("Sold After",  None,        "sold_after", None),
    ("Withdrawn",   None,        "withdrawn",  None),
    # On a PAST auction, "Available" means the lot did not sell.
    ("Available",   None,        "unsold",     None),
    ("Unsold",      None,        "unsold",     None),
])
def test_allsop_status(raw, price, status, hammer):
    assert allsop_status(raw, price) == (status, hammer)


def test_allsop_unsold_not_swallowed_by_sold():
    """Same substring trap as Bond Wolfe: 'Unsold' must not match 'Sold'."""
    assert allsop_status("Unsold", None)[0] == "unsold"


def test_allsop_ignores_a_price_on_a_non_sold_status():
    """If a stale price ever rides along on a withdrawn lot, don't call it a sale."""
    assert allsop_status("Withdrawn", "500000.00") == ("withdrawn", None)


def test_allsop_epoch_millisecond_auction_date():
    """auction_date is epoch ms at UK-LOCAL midnight, so it must be read in
    Europe/London. During BST that instant is 23:00Z the PREVIOUS day, and a UTC
    conversion reported every summer auction one day early — caught by checking
    against Allsop's own published dates, where winter events agreed and every
    BST event was off by one. A wrong auction_date corrupts the lots unique key."""
    # 2026-06-10 00:00 BST == 2026-06-09 23:00 UTC. Allsop publishes 10 June.
    assert allsop_date({"auction_date": 1781046000000}) == "2026-06-10"
    assert allsop_date({"auction_date": None}) is None
    assert allsop_date({}) is None


def test_allsop_winter_date_is_unchanged():
    """Outside BST, UTC and London agree — the fix must not shift those."""
    # 2026-02-11 00:00 GMT
    assert allsop_date({"auction_date": 1770768000000}) == "2026-02-11"


@pytest.mark.parametrize("lot,code", [
    ({"residential_property_types": ["Terraced House"]}, "T"),
    ({"residential_property_types": ["Semi-Detached House"]}, "S"),
    ({"residential_property_types": ["Flat / Block"]}, "F"),
    ({"commercial_property_types": ["Retail", "Mixed Use"]}, "O"),
    ({"allsop_propertytype": ["Office"]}, "O"),
    ({"commercial_property_types": ["Development", "Motor Trade"]}, "O"),
    ({"commercial_property_types": ["Ground Rent"]}, "O"),
    ({}, None),
])
def test_allsop_property_type(lot, code):
    assert allsop_type(lot) == code


@pytest.mark.parametrize("byline,code", [
    ("INVESTMENT - Freehold Mid Terrace House",           "T"),
    ("VACANT - Freehold End of Terrace House",            "T"),
    ("INVESTMENT/VACANT - Freehold Semi-Detached Building", "S"),
    ("VACANT - Freehold Link Detached House",             "D"),
    ("VACANT - Freehold Self-Contained Flat",             "F"),
])
def test_allsop_built_form_falls_back_to_byline(byline, code):
    """The residential catalogue labels most lots a bare 'House' with no built
    form — 133 of 301 in one auction — but the byline spells it out. Without
    this fallback those lots carry no type and drop out of like-for-like comps."""
    assert allsop_type({"residential_property_types": ["House"],
                        "main_byline": byline}) == code


def test_allsop_specific_label_beats_the_byline():
    """A real structured label must win; the byline is only a fallback."""
    assert allsop_type({"residential_property_types": ["Flat / Block"],
                        "main_byline": "Freehold Mid Terrace House"}) == "F"


def test_allsop_generic_house_with_no_byline_stays_unknown():
    """Guessing a built form we were never told would poison the comp set."""
    assert allsop_type({"residential_property_types": ["House"]}) is None


def test_allsop_single_figure_guide_is_not_a_range():
    """Allsop returns guide_price_upper == guide_price_lower for a plain
    '£750,000+' guide. Keeping it made 1,538 of 1,784 lots look range-guided
    and corrupted the guide-range analysis."""
    from scrape_allsop import parse_lots
    lot = {"allsop_lotid": "x", "allsop_address": "1 Test Street, London SW2 3LR",
           "allsop_propertypostcode": "SW2 3LR", "allsop_lotstatus": "Sold",
           "sale_price": "100000", "guide_price_lower": 750000,
           "guide_price_upper": 750000}
    rec = parse_lots([lot])[0]
    assert rec.guide_price == 750000
    assert rec.guide_price_max is None


def test_allsop_genuine_range_is_kept():
    from scrape_allsop import parse_lots
    lot = {"allsop_lotid": "y", "allsop_address": "2 Test Street, London SW2 3LR",
           "allsop_propertypostcode": "SW2 3LR", "allsop_lotstatus": "Sold",
           "sale_price": "100000", "guide_price_lower": 600000,
           "guide_price_upper": 650000}
    rec = parse_lots([lot])[0]
    assert (rec.guide_price, rec.guide_price_max) == (600000, 650000)


def test_allsop_description_joins_byline_and_features():
    lot = {"main_byline": "Freehold Shop and Residential Investment",
           "features": ["Comprising a ground floor shop", "Requires modernisation"]}
    d = allsop_desc(lot)
    assert "Freehold Shop" in d and "Requires modernisation" in d
    # It has to survive the condition classifier, which is the point of keeping it.
    assert classify_condition(d)[0] == "full_refurb"
