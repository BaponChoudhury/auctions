"""Parsing shared by the scrapers and the enrichment pass.

These live in one place because the scraper and enrich.py must agree on how a
house number is extracted — if they disagree, property_key stops matching the
PPD paon lookup and prior-sale enrichment silently returns nothing.
"""

import re

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
PRICE_RE = re.compile(r"£\s*([\d,]+)")

# Anchored at the start of the address on purpose. An unanchored \d+ would pull
# "169" out of "Land between 169 and 177 Spital Lane" and invent a property_key
# for a parcel of land that has no house number at all.
HOUSENO_RE = re.compile(r"^\s*(?:flat\s+\w+[,\s]+)?(\d+[a-z]?)\b", re.I)


def parse_price(text: str) -> int | None:
    """First £ amount in the text, as an int."""
    m = PRICE_RE.search(text or "")
    return int(m.group(1).replace(",", "")) if m else None


def parse_price_range(text: str) -> tuple[int | None, int | None]:
    """Guide prices come as '£175,000+', '£700,000 - £750,000' or '£95,000'."""
    amounts = [int(a.replace(",", "")) for a in PRICE_RE.findall(text or "")]
    if not amounts:
        return None, None
    return amounts[0], (amounts[1] if len(amounts) > 1 else None)


def parse_postcode(text: str) -> str | None:
    m = POSTCODE_RE.search(text or "")
    return f"{m.group(1).upper()} {m.group(2).upper()}" if m else None


def house_number(address: str) -> str | None:
    m = HOUSENO_RE.search(address or "")
    return m.group(1).lower() if m else None


def make_keys(address: str, postcode: str | None) -> tuple[str | None, str | None]:
    """postcode_sector ('ST16 2') and property_key ('14|ST16 2AB') for re-offer tracking."""
    if not postcode:
        return None, None
    out, inc = postcode.split(" ")
    sector = f"{out} {inc[0]}"
    houseno = house_number(address)
    return sector, (f"{houseno}|{postcode}" if houseno else None)


# SDL's card titles are free text ("Semi-detached House in Derby"). Map them onto
# the Land Registry PPD property_type codes so comps can be filtered like-for-like.
# Anything genuinely ambiguous maps to None, which widens the comp set rather than
# silently comparing a bungalow against terraced houses.
_TYPE_MAP = {
    "terraced house": "T",
    "end of terrace house": "T",
    "town house": "T",
    "semi-detached house": "S",
    "detached house": "D",
    "detached bungalow": "D",
    "flat": "F",
    "ground floor flat": "F",
    "studio flat": "F",
    "apartment": "F",
    "maisonette": "F",
    "duplex": "F",
    "retirement property": "F",
    "land": "O",
    "commercial property": "O",
    "block of apartments": "O",
    "house of multiple occupation": "O",
    "residential development": "O",
    "mixed use": "O",
    "warehouse": "O",
    "retail property (high street)": "O",
    "light industrial": "O",
    "pub": "O",
    "shop": "O",
    "hotel": "O",
}


def property_type_code(card_title: str) -> str | None:
    """'Semi-detached House in Derby' -> 'S'. Unknown/ambiguous -> None."""
    if not card_title:
        return None
    # Strip the trailing ' in <Town>' that every SDL card title carries.
    label = re.sub(r"\s+in\s+[^,]+$", "", card_title.strip(), flags=re.I).lower()
    return _TYPE_MAP.get(label)


def classify_status(result_text: str) -> tuple[str, int | None]:
    """Map SDL's result wording to a status plus a hammer price where one exists.

    The vocabulary here was taken from a live event page (224 lots), not guessed:
      'Sold at Auction £72,000' / 'Sold Prior to Auction' / 'Sold After Auction'
      'Withdrawn' / 'Withdrawn Post' / 'Postponed'
      'Re-entry to a future auction'   <- SDL's wording for "did not sell"
    A price is only trusted as the hammer price on a sold status; 'Withdrawn £X'
    does appear and that figure is not a sale.
    """
    t = (result_text or "").replace("\xa0", " ").strip()
    low = t.lower()
    price = parse_price(t)

    if "sold prior" in low:
        return "sold_prior", price
    if "sold after" in low:
        return "sold_after", price
    if "sold" in low:
        return "sold", price
    if "withdrawn" in low:
        return "withdrawn", None
    if "postponed" in low:
        return "postponed", None
    if "re-entry" in low or "reentry" in low or "unsold" in low or "not sold" in low:
        return "unsold", None
    return "listed", None
