# =============================================================================
# pages/3_Your_own_data.py: the two CSV formats and running locally
# =============================================================================
# The P&L and KPI file formats (columns from the loader, categories from the
# engine, example rows read from the sample files), what happens to each
# kind of row (the engine's own notes, from src.notes.row_handling), the
# limits, privacy, and how to run the project on your own machine. No figure
# is typed here: limits and names come from the engine and config.
# =============================================================================

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import CASH_KPI_METRIC, CASH_KPI_SCALE, GROSS_MARGIN_KPI_METRIC, REPO_URL
from src.pipeline import (
    CASH_REVENUE_MULTIPLE, CASH_UNITS, CATEGORIES, KPI_COLUMNS, MAX_NAME_LENGTH,
    OPTIONAL_KPI_COLUMNS, PNL_COLUMNS, SIGN_WORD, row_handling,
)
from streamlit_app.lib.content import sample_rows
from streamlit_app.lib.display import table_html
from streamlit_app.lib.inputs import MAX_MB, MAX_PNL_LINES
from streamlit_app.lib.theme import header_html, inject_css

PNL_MEANING = {
    "line_item": "The line's name, as the board should read it.",
    "category": "One of " + ", ".join(CATEGORIES[:-1]) + f" or {CATEGORIES[-1]}.",
    "actuals": "The month's actual, in pounds.",
    "budget": "The month's budget, in pounds.",
    "prior_year": "The same month last year, in pounds.",
}
KPI_MEANING = {
    "metric": "The KPI's name, with its unit in brackets if it has one.",
    "actual": "This month's value.",
    "target": "The target for the month.",
    "prior_year": "The same month last year; leave it blank if there is none.",
}


def _required(column: str, required: tuple[str, ...]) -> str:
    return "Yes" if column in required else "No"


st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(header_html(
    "Your own data",
    "The two files the pack is built from, and how to run it on your own numbers."),
    unsafe_allow_html=True)

st.markdown("#### The P&L file")
st.markdown(
    "One row for each line of the P&L, under a header row. Column names are not case "
    "sensitive, and their order does not matter.")
st.markdown(table_html(
    ["Column", "Required", "What it holds"],
    [[c, _required(c, PNL_COLUMNS), PNL_MEANING[c]] for c in PNL_COLUMNS],
    wrap=(2,)), unsafe_allow_html=True)
st.markdown(
    "Amounts may include thousands separators, a pound sign, or brackets for a negative, and "
    "a trailing minus sign is read as negative too. Leave out subtotal rows: revenue, COGS, "
    "gross profit, opex and EBIT are computed from the lines.")
header, rows = sample_rows("pnl")
st.markdown(table_html(header, rows, numeric=(2, 3, 4),
                       caption="The first rows of the sample P&L file, exactly as in the file."),
            unsafe_allow_html=True)

st.markdown("#### The KPI file")
st.markdown(
    "One row for each KPI, under a header row. The file is optional: without it, the KPIs "
    "show only the gross margin from the P&L, and there is no cash balance.")
kpi_columns = KPI_COLUMNS + OPTIONAL_KPI_COLUMNS
st.markdown(table_html(
    ["Column", "Required", "What it holds"],
    [[c, _required(c, KPI_COLUMNS), KPI_MEANING[c]] for c in kpi_columns],
    wrap=(2,)), unsafe_allow_html=True)
units = " or ".join(CASH_UNITS)
sample_unit = next(unit for unit, scale in CASH_UNITS.items() if scale == CASH_KPI_SCALE)
st.markdown(
    f"The cash balance is the row named {CASH_KPI_METRIC}, or Cash balance with any unit in "
    f"brackets. You say when you run whether the file states it in {units}; the sample states "
    f"it in {sample_unit}. Two checks warn if the choice looks wrong: a unit in the KPI's name that "
    f"disagrees with it, and a balance more than {CASH_REVENUE_MULTIPLE:,} times the month's "
    "revenue. They warn; they never stop the pack.")
st.markdown(
    f"A gross margin row ({GROSS_MARGIN_KPI_METRIC}) is not needed and is ignored if present: "
    "the gross margin is computed from the P&L, so the pack has one source for each number.")
header, rows = sample_rows("kpis", n=20)
st.markdown(table_html(header, rows, numeric=(1, 2, 3), wrap=(0,),
                       caption="The sample KPI file, exactly as in the file."),
            unsafe_allow_html=True)

st.markdown("#### What happens to each row")
st.markdown(
    "Nothing is dropped silently. Every row the pack cannot use as it stands produces a "
    "note: shown before review, printed by the command line, and listed in the PDF's review "
    "notes. The notes below are written by the same code that writes them for your files.")
st.markdown(table_html(
    ["In the file", "What the pack does", "The note"],
    [[situation, action, note] for situation, action, note in row_handling()],
    wrap=(0, 1, 2)), unsafe_allow_html=True)

st.markdown("#### Limits")
st.markdown(
    f"- Each file up to {MAX_MB} MB, and the P&L up to {MAX_PNL_LINES:,} lines.\n"
    "- One period per file: the month the pack is for. There is no period column; you name "
    "the period when you run.\n"
    "- Pounds sterling only.\n"
    f"- Names longer than {MAX_NAME_LENGTH} characters are kept, with a note, and wrap "
    "inside their column.")

st.markdown("#### Privacy")
st.markdown(
    "Files you upload are written only to your session's own temporary folder on the "
    "server, read once to build the pack, and then deleted. The pack keeps their SHA-256 "
    "hashes, so the exact files can be identified later without being kept. The PDFs and "
    "audit lines your session produces are not kept on purpose: they are deleted when you "
    "build a new draft or start again, and the server's temporary storage is cleared when "
    "the app restarts.")
st.markdown(
    "An API key, if you give one, is held in the server's memory for your session only, used "
    "to make the call, and never stored or logged. When the model drafts the commentary, it "
    "receives only the formatted figures and names in the pack facts, never your files.")
st.page_link("pages/4_How_its_built.py",
             label="How it's built: exactly what the model receives for the sample",
             icon=":material/build:")

st.markdown("#### Running locally")
st.markdown(
    "To keep your files and your key on your own machine, run the project locally, from "
    f"its repository at [{REPO_URL.removeprefix('https://')}]({REPO_URL}):")
st.code(f"git clone {REPO_URL}.git\n"
        f"cd {REPO_URL.rsplit('/', 1)[-1]}\n"
        "pip install -r requirements.txt\n"
        "python main.py --draft-only\n"
        "python main.py\n"
        "streamlit run streamlit_app/Home.py", language=None)
st.markdown(
    "The first two commands copy the repository and enter its folder; the third installs the "
    "requirements. `python main.py --draft-only` builds a "
    "DRAFT of the sample with its review notes. `python main.py` takes you through the "
    f"review in the terminal and asks for your name and {SIGN_WORD}. The last command runs "
    "this app on your machine.")
st.markdown(
    "For your own files, add `--pnl` and `--kpis` with their paths, `--entity` and "
    "`--period`, and `--cash-unit pounds` if the KPI file states cash in pounds; "
    "`python main.py --help` lists every option. The model is used only with `--use-model` "
    "and a key in the environment or a .env file, never one typed on the command line.")
st.page_link("pages/2_Board_pack.py", label="Board pack: run your own files here instead",
             icon=":material/description:")
