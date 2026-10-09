# =============================================================================
# pages/1_How_the_pack_is_built.py: the method, for a finance reader
# =============================================================================
# W1 placeholder. W4 writes the content: materiality as a rule, Fav/(Adv),
# the drivers table, what the commentary may and may not say, why the model
# is told not to explain causes (the Ingredients finding), and sign-off.
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
    "How the pack is built",
    "The method in plain terms, for the person who will sign the pack."),
    unsafe_allow_html=True)
st.write(
    "This page will explain how the pack is put together: how a rule decides what is "
    "material, how favourable and adverse variances are shown, where the drivers table "
    "comes from, what the commentary may and may not say, and what a reviewer confirms "
    "when they sign. Until then, the Board pack page shows the method at work on the sample.")
