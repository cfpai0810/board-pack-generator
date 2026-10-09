# =============================================================================
# pages/4_How_its_built.py: the technical and governance story
# =============================================================================
# W1 placeholder. W4 writes the content: the pipeline diagram, the tests,
# the audit trail and determinism.
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
    "How it's built",
    "The pipeline, the tests and the audit trail behind every pack."),
    unsafe_allow_html=True)
st.write(
    "This page will show the pipeline from the source files to the signed PDF, the test "
    "suite that pins every figure, the audit trail written for each review and render, and "
    "why the same signed pack always renders to the same bytes.")
