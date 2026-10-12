# =============================================================================
# views/4_How_its_built.py: the pipeline, the tests, the audit trail, the limits
# =============================================================================
# The technical and governance story for a finance reader: the seven steps
# and what each owns, the test counts (written by the test run), the
# determinism of a signed pack (checked at page load against the worked
# example's audit line), its audit lines as written, what the model receives
# for the sample (from the engine), and the limitations, one of them shown
# by the engine itself. No figure is typed here.
# =============================================================================

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import SIGN_WORD, model_prompt, soft_check_example
from streamlit_app.lib.content import sample_pack, test_counts, worked_example
from streamlit_app.lib.display import flow_html, table_html
from streamlit_app.lib.theme import header_html, inject_css

STEPS = [
    ("Load", "Reads the two CSV files into typed records. Every amount becomes an exact "
             "decimal; a row that cannot be read is noted, never dropped silently."),
    ("Validate", "Checks that the records would not mislead: no revenue, no costs, unnamed "
                 "or duplicate lines. It writes a data note and carries on."),
    ("Compute", "Every variance, subtotal and margin, and the gross margin KPI, from the "
                "lines."),
    ("Assemble", "The materiality rule, where each item is discussed, the drivers, and the "
                 "four sections of the pack."),
    ("Draft", "The commentary, by the template or the model (Claude, via the Anthropic API), inside the "
              "figures; then the numeric, cause and direction checks."),
    ("Review", f"Edits, flags, sign-off with a name and {SIGN_WORD}, and the review line in "
               "the audit trail."),
    ("Render", "The PDF, DRAFT or FINAL, and the rendered line with the file's SHA-256."),
]

pack = sample_pack()
example = worked_example()
counts = test_counts()

st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(header_html(
    "How it's built",
    "The pipeline, the tests and the audit trail behind every pack."),
    unsafe_allow_html=True)

st.markdown("#### The pipeline")
st.markdown(
    "Seven steps, each owning one part of the work. One function, `run_pipeline`, runs them "
    "in order for the command line and for this app alike, so both produce the same pack "
    "from the same inputs.")
st.markdown(flow_html(STEPS), unsafe_allow_html=True)

st.markdown("#### Tests")
if counts:
    st.markdown(
        f"{counts['total']:,} tests pin the behaviour"
        + (f", {counts['by_suite']['engine']:,} on the engine and "
           f"{counts['by_suite']['web']:,} on this website" if "by_suite" in counts else "")
        + ", from reading an amount in a CSV file to signing a pack. The whole suite runs on "
        "every push and pull request, in continuous integration on GitHub. By area:")
    st.markdown(table_html(
        ["Area", "Tests"], [[a["area"], f"{a['tests']:,}"] for a in counts["by_area"]],
        numeric=(1,), wrap=(0,),
        caption="Written by the test run itself (generated/test_counts.json), not typed here."),
        unsafe_allow_html=True)
else:
    st.markdown(
        "The test suite pins the behaviour, from reading an amount in a CSV file to signing "
        "on this website. Its counts by area appear here once a full run of the suite has "
        "passed and written them (generated/test_counts.json).")

st.markdown("#### Determinism")
st.markdown(
    "A signed pack renders to identical bytes every time. The PDF is built in reportlab's "
    "invariant mode, which leaves out the creation time and any random identifiers, and a "
    "FINAL is dated by its sign-off rather than by the clock. So the hash recorded when a "
    "pack is signed proves which file was signed, and the file can be checked against it at "
    "any time; a test re-renders a signed pack and compares the bytes. For the worked "
    "example:")
recorded = example["rendered"]["pdf_sha256"]
match = "They match." if example["pdf_sha256"] == recorded else "They do not match."
st.markdown(table_html(
    ["", "SHA-256"],
    [["The PDF, hashed as this page loaded", example["pdf_sha256"]],
     ["The hash in its rendered audit line", recorded]],
    wrap=(0, 1), caption=match), unsafe_allow_html=True)

st.markdown("#### The audit trail")
st.markdown(
    "Every review and every rendered PDF appends one line to an append-only JSONL file. "
    "These are the worked example's two lines, exactly as written:")
st.code(example["audit_text"], language=None, wrap_lines=True)
st.markdown(
    "The review line holds the input files' hashes, the code version, the thresholds, the "
    "material items and the drivers, each section's draft and final text, every flag, and "
    "what was acknowledged at sign-off. The rendered line holds the PDF's file name and "
    "SHA-256. The run id links the two.")

st.markdown("#### What the model sees")
system, user = model_prompt(pack)
st.markdown(
    "When the model drafts the commentary, this is everything it receives for the sample, "
    "built by the engine: formatted figures and names, and what to write for each section. "
    "The files themselves are never sent.")
st.code(user, language=None, wrap_lines=True)
with st.expander("The system prompt: the rules the model must follow"):
    st.code(system, language=None, wrap_lines=True)

st.markdown("#### Limitations")
loose = soft_check_example(pack)
soft = (
    f"- **The checks are soft.** The numeric check reads a figure to the precision it is "
    f"written in, so {loose.coarse} raises no flag against a revenue budget of {loose.budget}. "
    "It catches invented figures, not loose ones: precision is the reviewer's check.\n"
    if not loose.flagged else
    "- **The checks are soft.** The numeric, cause and direction checks flag text for the "
    "reviewer; they never stop a pack, and the reviewer remains the check.\n")
st.markdown(
    soft +
    "- **KPI direction is unknown.** The KPI file does not say whether higher is better, so "
    "KPI differences are shown as plain differences, not Fav/(Adv).\n"
    "- **One period, one currency.** Each file holds one month, and every amount is read in "
    "the one currency chosen for the run (GBP, EUR, USD, JPY or CHF); nothing is converted.\n"
    "- **The model adds little.** Once the figures, the selection and the attribution are "
    "computed, the model's wording adds little that the template does not. That is why the "
    "template is the default and the model an option.")
st.page_link("views/1_How_the_pack_is_built.py",
             label="How the pack is built: the method, for the reviewer",
             icon=":material/menu_book:")
