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


def test_both_sources_emit_the_same_record_shape():
    """enrich.py and the schema depend on this staying true as sources are added."""
    import dataclasses
    from scrape_sdl import LotRecord
    import scrape_bondwolfe
    assert scrape_bondwolfe.LotRecord is LotRecord
    fields = {f.name for f in dataclasses.fields(LotRecord)}
    assert {"source", "source_lot_id", "address_raw", "postcode", "property_key",
            "guide_price", "hammer_price", "status", "property_type"} <= fields
