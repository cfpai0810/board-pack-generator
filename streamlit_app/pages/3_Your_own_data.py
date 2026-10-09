# =============================================================================
# pages/3_Your_own_data.py: the two CSV formats and running locally
# =============================================================================
# W1 placeholder. W4 writes the content: the P&L and KPI file formats, the
# rules for blank and unreadable rows, and how to run the project locally.
# =============================================================================

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.lib.theme import header_html, inject_css

st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(header_html(
    "Your own data",
    "The two files the pack is built from, and how to run it on your own numbers."),
    unsafe_allow_html=True)
st.write(
    "This page will describe the two CSV files the pack needs (a P&L with actual, budget "
    "and prior year by line, and a KPI file), what happens to blank or unreadable rows, and "
    "how to run the generator on your own machine so your files never leave it.")
