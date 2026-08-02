"""Smoke test for the browser UI.

Runs the Streamlit app headlessly and clicks Check, so a broken import or a
runtime error in the app surfaces here rather than in front of the user.

Marked slow: it trains the model and scans the Land Registry extracts.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent
APP = ROOT / "ui" / "app.py"

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.mark.slow
def test_ui_loads_and_predicts():
    at = AppTest.from_file(str(APP), default_timeout=600)
    at.run()
    assert not at.exception, f"app failed on load: {at.exception}"

    # Defaults are ST16 3RD / semi / 3 beds / £95,000 guide.
    at.button[0].click().run()
    assert not at.exception, f"app failed on Check: {at.exception}"

    body = " ".join(str(m.value) for m in at.markdown) \
        + " ".join(str(s.value) for s in at.success) \
        + " ".join(str(w.value) for w in at.warning)
    # It must reach a verdict one way or the other.
    assert ("agree on" in body.lower() or "do not overlap" in body.lower()), body[:400]
    # And it must have found Land Registry evidence for the sector.
    assert "Land Registry" in body


@pytest.mark.slow
def test_ui_rejects_a_partial_postcode():
    at = AppTest.from_file(str(APP), default_timeout=600)
    at.run()
    at.text_input[0].set_value("ST16").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("full postcode" in str(e.value) for e in at.error), \
        "a partial postcode should be rejected, not silently priced"
