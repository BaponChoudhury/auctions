"""Browser UI for the auction price model.

  streamlit run ui/app.py

Enter a postcode, property type and (optionally) a guide price. Shows the three
independent estimates and where they overlap, same logic as src/predict_lot.py.
"""

import pathlib
import sys
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geo import load_cache                                    # noqa: E402
from predict_lot import (CATS, FEATURES, NAME, build_model,   # noqa: E402
                         comps, ppd_sector_index, sector_of)

DATA = ROOT / "data"
UPLIFT_MID, UPLIFT_LO, UPLIFT_HI = 1.20, 1.10, 1.49

st.set_page_config(page_title="Auction price check", page_icon="🏠", layout="centered")


@st.cache_resource(show_spinner="Training the model (once per session)...")
def get_model():
    df = pd.read_csv(DATA / "features.csv")
    df = df[(df.hammer_price > 1000) & df.property_type.isin(["D", "S", "T", "F"])]
    return build_model(df)


@st.cache_resource(show_spinner="Loading postcode areas...")
def get_geo():
    return load_cache()


@st.cache_data(show_spinner="Reading Land Registry sales for this area...")
def get_comps(sector: str, ptype: str):
    """Cached per sector+type: the first lookup scans the PPD extracts."""
    idx = ppd_sector_index({sector})
    return comps(idx, sector, ptype, date.today().isoformat())


@st.cache_data(show_spinner="Loading auction history...")
def get_auction_lots():
    import json
    rows = []
    for p in ("sdl_all", "bw_full", "allsop_all", "emson_all"):
        f = DATA / f"{p}.jsonl"
        if f.exists():
            rows += [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
    return [r for r in rows if r.get("hammer_price")]


st.title("🏠 Auction price check")
st.caption("What is this lot likely to fetch under the hammer?")

c1, c2, c3 = st.columns([2, 2, 1])
postcode = c1.text_input("Postcode", "ST16 3RD",
                         help="Full postcode, e.g. ST16 3RD")
ptype = c2.selectbox("Property type", ["S", "T", "D", "F"],
                     format_func=lambda t: NAME[t])
beds = c3.number_input("Beds", 0, 10, 3, help="0 if unknown")
guide = st.number_input("Guide price (£) — optional, 0 to skip",
                        0, 5_000_000, 95_000, step=5_000)

if st.button("Check", type="primary", use_container_width=True):
    pc = postcode.upper().strip()
    sector = sector_of(pc)
    if not sector:
        st.error("That does not look like a full postcode. Try e.g. ST16 3RD.")
        st.stop()

    model, err, n_tr, n_te, mdape = get_model()
    geo = get_geo().get(pc) or {}
    med, cnt, iqr = get_comps(sector, ptype)

    if med is None:
        st.error(f"No Land Registry sales of that type in sector {sector} — "
                 "the model has nothing to anchor on. Try a different type or "
                 "check the postcode.")
        st.stop()

    district = geo.get("admin_district") or ""
    region = geo.get("region") or ""
    st.markdown(f"**{NAME[ptype]}** in **{pc}** — {district}, {region}  \n"
                f"Land Registry: {cnt} sales of this type in {sector} over 24 "
                f"months, median **£{med:,}**")

    row = pd.DataFrame([{"comp_median": med, "comp_count": cnt,
                         "comp_iqr": iqr if iqr else np.nan,
                         "bedrooms": beds if beds else np.nan,
                         "property_type": ptype, "region": region,
                         "district": district}])
    for c in CATS:
        row[c] = row[c].astype("category")
    point = float(np.exp(model.predict(row[FEATURES + CATS])[0]))
    lo50, hi50 = point / np.percentile(err, 75), point / np.percentile(err, 25)

    lots = get_auction_lots()
    out = pc.split()[0]
    near = [l["hammer_price"] for l in lots
            if l.get("property_type") == ptype
            and (l.get("postcode") or "").startswith(out)]
    comp_lo = comp_hi = None
    if len(near) >= 5:
        a = np.array(sorted(near))
        comp_lo, comp_hi = np.percentile(a, 25), np.percentile(a, 75)

    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Model estimate", f"£{point:,.0f}",
              help=f"Median absolute error {mdape:.0f}% on {n_te:,} unseen auctions")
    if guide:
        m2.metric("From the guide", f"£{guide*UPLIFT_MID:,.0f}",
                  help="Guide x1.20, the locally measured uplift")
    if comp_lo:
        m3.metric("Comparables", f"£{np.median(a):,.0f}",
                  help=f"{len(near)} auction sales in {out}")

    lows = [lo50] + ([guide * UPLIFT_LO] if guide else []) + \
           ([comp_lo] if comp_lo is not None else [])
    highs = [hi50] + ([guide * UPLIFT_HI] if guide else []) + \
            ([comp_hi] if comp_hi is not None else [])
    ov_lo, ov_hi = max(lows), min(highs)

    st.subheader("The three estimates")
    rows = [{"method": "Model", "low": lo50, "high": hi50}]
    if guide:
        rows.append({"method": "From guide", "low": guide * UPLIFT_LO,
                     "high": guide * UPLIFT_HI})
    if comp_lo is not None:
        rows.append({"method": "Comparable sales", "low": comp_lo, "high": comp_hi})
    st.dataframe(
        pd.DataFrame(rows).assign(
            range=lambda d: d.apply(lambda r: f"£{r.low:,.0f} – £{r.high:,.0f}", axis=1)
        )[["method", "range"]],
        hide_index=True, use_container_width=True)

    if ov_lo <= ov_hi:
        st.success(f"### All three agree on £{ov_lo:,.0f} – £{ov_hi:,.0f}\n"
                   f"Bid in that range. **Walk away above £{ov_hi:,.0f}.**")
    else:
        st.warning("### The three do not overlap\n"
                   "That usually means the lot is unusual, the guide is bait, or "
                   "the local sample is too thin. Read the legal pack — do not "
                   "average them.\n\n"
                   f"Widest span £{min(lows):,.0f} – £{max(highs):,.0f}")

    st.caption(
        f"Hammer price only — buyer's fees and any works are on top. "
        f"Model median absolute error is {mdape:.0f}%, measured on {n_te:,} later "
        f"auctions it never trained on. It prices an ordinary lot and cannot see "
        f"condition, tenure or title problems."
    )
