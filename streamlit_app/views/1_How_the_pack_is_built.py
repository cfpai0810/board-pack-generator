# =============================================================================
# views/1_How_the_pack_is_built.py: the method, for a finance reader
# =============================================================================
# For the reviewer, who signs the pack: what is computed, what a rule
# decides, how variances read, why attribution is computed, what the
# commentary may and may not say, and what signing means. Every figure
# quoted is the sample pack's, built by the engine at page load
# (lib/content.sample_pack); none is typed here, and a test fails if one is.
# =============================================================================

import html
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import NARRATIVE_MODEL
from src.pipeline import (
    DRIVERS_NOTE, SIGN_WORD, count_words, drivers_header, drivers_rows, fav_adv_examples, headline,
    headline_sentence, material_items, placement_example, thresholds,
)
from streamlit_app.lib.content import sample_pack
from streamlit_app.lib.display import drivers_table_html, table_html
from streamlit_app.lib.theme import header_html, inject_css

pack = sample_pack()
top = headline(pack)
abs_text, pct_text = thresholds(pack)
items = material_items(pack)

st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(header_html(
    "How the pack is built",
    "The method in plain terms, for the reviewer who will sign the pack."),
    unsafe_allow_html=True)
st.markdown(
    f"Every example on this page comes from the sample pack for {pack.entity}, "
    f"{pack.period}, built by the engine when the page loaded. No figure here is typed in.")

st.markdown("#### Figures")
st.markdown(
    "Every figure is computed in Python from two files: a P&L giving each line's actual, "
    "budget and last year's figure, and a short file of KPIs. Subtotals are computed, never read "
    "in: revenue, COGS and opex are the sums of their lines, gross profit is revenue less "
    "COGS, and EBIT is gross profit less opex. "
    f"In the sample, {top['revenue_lines']} to revenue of {top['revenue']}, and EBIT is "
    f"{top['ebit']} against {top['ebit_budget']}.")
st.markdown(
    "Amounts are held as exact decimals, never as floating point numbers, and rounded only "
    "when they are shown. The gross margin is computed from the P&L too: a gross margin row "
    "in the KPI file is ignored, so each number in the pack has one source.")

st.markdown("#### The headline, the tiles and the charts")
st.markdown(
    "Page 1 of the pack opens with a headline, a summary line under it and four tiles, and "
    "the pack carries two charts: the budget-to-actual bridge and each line's effect on "
    "profit. All of them are computed from the figures by code, the same way every time; "
    "the commentary does not write them and the reviewer cannot edit them. The headline "
    "gives EBIT against budget and last year: on the sample, "
    f"“{headline_sentence(pack)}” The summary line says how far revenue, COGS and "
    "opex moved against budget, and how revenue and the gross margin compare with last "
    "year. The tiles give revenue, gross profit, the gross margin and EBIT, each against "
    "budget and last year. The bridge steps from budget EBIT to actual EBIT through revenue, "
    "COGS and opex, and the effects chart ranks each line by its effect on profit. The "
    "numeric check runs on this text as well, and a test requires it to raise no flag.")

st.markdown("#### Materiality")
st.markdown(
    "What the pack discusses is decided by a rule, not by the model (Claude, via the Anthropic API). A line or "
    "subtotal is "
    f"material when its variance against budget is {abs_text} or more, or {pct_text} of "
    "budget or more. The percentage test is not applied across a change of sign, where a "
    "percentage means nothing. Both thresholds can be changed for your own run on the Board "
    "pack page.")
st.markdown(f"On the sample, the rule finds {count_words(len(items))} material items:")
st.markdown(table_html(
    ["Item", "Type", "Fav/(Adv) vs budget £", "%", "Discussed in"],
    [[i.name, i.kind, i.variance, i.variance_pct, i.placement] for i in items],
    numeric=(2, 3), wrap=(4,)), unsafe_allow_html=True)
example = placement_example(pack)
st.markdown(
    "Each material item is discussed once. A material line under a material subtotal goes to "
    "the P&L commentary, because the executive summary already covers its subtotal; a "
    "material line under a subtotal that is not material goes to the executive summary, so "
    "it is not lost." + (f" {example}" if example else ""))

st.markdown("#### Favourable and adverse")
st.markdown(
    "Variance columns are headed Fav/(Adv): a favourable variance is shown plain and an "
    "adverse one in brackets, so the reader never has to work out whether a positive number "
    "is good news. For revenue, below budget is adverse. For a cost, above budget (an "
    "overspend) is adverse, even though the number went up. Two lines from the sample:")
st.markdown(table_html(
    ["Line", "Type", "Actual £", "Budget £", "Fav/(Adv) £", "Reading"],
    [[e.name, e.kind, e.actual, e.budget, e.shown, e.reading] for e in fav_adv_examples(pack)],
    numeric=(2, 3, 4), wrap=(5,)), unsafe_allow_html=True)
st.markdown(
    "n/m stands for not meaningful: the comparator is zero, or the figure changed sign, so a "
    "percentage would mislead.")

st.markdown("#### Drivers")
st.markdown(
    "Under the executive summary, a small table shows the main drivers of each material "
    "profit subtotal: the lines whose budget variances moved it most, each as its effect on "
    "profit, in Fav/(Adv) form. On the sample:")
st.markdown(drivers_table_html(drivers_rows(pack), drivers_header(pack.currency)),
            unsafe_allow_html=True)
st.markdown(f'<p class="bp-note">{html.escape(DRIVERS_NOTE)}</p>', unsafe_allow_html=True)
st.markdown(
    "**Why it is computed rather than written.** In live tests the model was given the "
    "correct figures, with the drivers grouped as lines that lowered profit. In two of three "
    "runs it still described the ingredients overspend as an offset, and the very first live "
    "run had made the same error. A "
    "commentary that gets the direction of a variance wrong is worse than none, and a "
    "reviewer reading quickly may not catch it. So attribution moved into code: the table "
    "above is arithmetic, the commentary no longer attributes, and a direction check flags "
    "any offset language the model still writes.")

st.markdown("#### The commentary")
st.markdown(
    "The commentary says what moved and by how much. It does not say why: causes, "
    "judgements, recommendations and forecasts belong to the reviewer, who adds them at "
    "review. The template drafts it by default: it needs no key and writes the same "
    "sentences from the same figures every time. With your own API key, the model "
    f"({NARRATIVE_MODEL}) can draft it instead, from the same figures and inside the same "
    "checks. Only the formatted figures and names are sent to it, never your files.")
st.markdown(
    "Every section is checked when it is drafted and again whenever it is edited. Four kinds "
    "of flag can be raised:\n"
    "- **Numeric**: a figure in the text matches no figure in the pack. This checks the "
    "reviewer's text too.\n"
    "- **Cause**: the model's text gives a reason, such as \"due to\", which only the "
    "reviewer can know.\n"
    "- **Direction**: the model's text calls a line an offset when it did not offset "
    "anything.\n"
    "- **Glyph**: a character the PDF's font cannot print.")
st.markdown(
    "Flags never block. They are shown beside the text, listed before sign-off, and any "
    "still open when the pack is signed are recorded as acknowledged.")

st.markdown("#### Review and sign-off")
st.markdown(
    "Every pack starts as a DRAFT. The reviewer reads each section and may edit its text; "
    "the figures and the tables cannot be edited. Flags update as they type. To sign, they "
    f"give their name and type {SIGN_WORD} exactly; any other word leaves the pack a DRAFT. "
    "A DRAFT carries a watermark on every page and a page of review notes listing what is "
    "outstanding. A FINAL carries the reviewer's name and the time of sign-off, and its "
    "commentary can no longer be changed: a signed pack is changed only by a new run.")
st.markdown(
    "Each review, and each PDF rendered, adds one line to an audit trail. The lines of one "
    "run share a run id, and the rendered line records the PDF's SHA-256, so the signed file "
    "can always be matched to its record.")
st.page_link("views/2_Board_pack.py", label="Board pack: a signed example, and a run of your own",
             icon=":material/description:")
st.page_link("views/4_How_its_built.py", label="How it's built: the audit trail and what the "
             "model sees", icon=":material/build:")
