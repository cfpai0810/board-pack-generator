# Board Pack Generator

Build a monthly management pack for a board from a P&L and a short file of
KPIs: the figures computed in Python, the items that matter selected by a
rule, the commentary drafted inside those figures, and a PDF that stays a
DRAFT until a named person reviews it and signs. An optional AI layer can
draft the commentary, but every figure, every selection and every
attribution is the code's.

**Live demo:** [board-pack-generator.streamlit.app](https://board-pack-generator.streamlit.app)

The data in this repository is illustrative sample data for a fictional
entity.

---

## What it does

You supply two CSV files: a P&L with the actual, budget and prior year for
each line, and a KPI file (optional). The tool computes every subtotal,
variance and margin, flags what is material against budget by rule, places
each material item in the executive summary or the P&L commentary, computes
the drivers of each material profit subtotal, and drafts the commentary from
those figures only. A reviewer then edits the commentary, sees flags update as
they type, and signs with their name and the word SIGN. The output is a PDF
board pack (DRAFT or FINAL) and a JSONL audit trail that links each review to
the exact file it produced.

Two ways to use it:

**CLI.** Run `python main.py` for a guided review at the terminal, or
`python main.py --draft-only` for a DRAFT with its review notes and no
prompts. The PDF and the audit trail are written to `output/`.

**Web app.** Run `streamlit run streamlit_app/Home.py` for a five-page
Streamlit app. A signed worked example opens with no run and no key; the
Board pack page builds a draft from the sample or your own files, takes you
through review and sign-off, and offers the PDF and the audit lines. To have
the model draft the commentary, enter your own Anthropic key in the sidebar.

---

## The design rule

Python computes. A rule selects. The commentary narrates. A person signs.

**Figures.** Every figure is computed from the two files, in exact decimals,
never floating point. Subtotals are computed, never read in. The gross margin
is computed from the P&L, and a gross margin row in the KPI file is ignored,
so each number in the pack has one source.

**Materiality.** A line or subtotal is material when its variance against
budget reaches either threshold (by default £50,000 or 10% of budget; the
percentage test is not applied across a change of sign). Each material item
is discussed once: a material line under a material subtotal goes to the P&L
commentary, any other material line to the executive summary.

**Favourable and adverse.** Variance columns are headed Fav/(Adv): favourable
variances plain, adverse in brackets, and for a cost an overspend is adverse.
A percentage across a change of sign or over a zero comparator is shown as
n/m.

**Drivers are computed, not written.** In live tests the model was given the
correct figures, with the drivers grouped as lines that lowered profit, and in
two of three runs it still described an ingredients overspend as an offset;
the very first live run had made the same error. So attribution moved into
code: a drivers table under the executive summary shows each line's effect on
profit, the commentary no longer attributes, and a direction check flags any
offset language the model still writes.

**The commentary.** It says what moved and by how much, never why: causes,
judgements, recommendations and forecasts belong to the reviewer. The
template drafts it by default; the model is an option inside the same
figures and the same checks. Four kinds of flag can be raised (numeric,
cause, direction, glyph). Flags never block; any still open at sign-off are
recorded as acknowledged.

---

## The two data files

**P&L** (`data/pnl.csv`): `line_item`, `category` (revenue, cogs or opex),
`actuals`, `budget`, `prior_year`. One row per line; no subtotal rows.

**KPIs** (`data/kpis.csv`, optional): `metric`, `actual`, `target`, and
`prior_year` (optional). The cash balance is the row named
`Cash balance (GBP 000s)`, or `Cash balance` with any unit in brackets; you
say when you run whether the file states it in thousands or pounds.

Column names are matched case-insensitively. Amounts may carry thousands
separators, a pound sign, brackets or a trailing minus for a negative. A row
that cannot be read is never dropped silently: it produces a note, and rows
left out of the totals are named in a box above the P&L table.

See the Your own data page in the web app for the full formats, example rows,
and a table of what happens to blank, unnamed, unreadable and long rows,
written by the same code that writes the notes.

---

## How a request becomes a result

```
pnl.csv                    kpis.csv (optional)
   |                            |
   v                            v
step1_load (CSV to typed records, exact decimals, a note for every unreadable row)
               |
               v
step2_validate (no revenue, no costs, unnamed, duplicate or long names: warns, carries on)
               |
               v
step3_compute (variances, subtotals, margins, the gross margin KPI)
               |
               v
step4_assemble (materiality rule, placement, drivers, the four sections)
               |
               v
step5_narrate (template or model, inside the figures; numeric, cause, direction checks)
               |
               v
step6_review (edits, flags, sign-off with a name and SIGN, the review audit line)
               |
               v
step7_render (DRAFT or FINAL PDF, the rendered audit line with the PDF's SHA-256)
```

`run_pipeline` in `src/pipeline.py` runs these steps for the CLI and the web
app alike, so both produce the same pack from the same inputs.

---

## Review, sign-off and determinism

Every pack starts as a DRAFT, with a watermark on every page and a page of
review notes listing what is outstanding. The reviewer may edit the
commentary, never the figures or the tables. A pack is signed only with a
reviewer name and the word SIGN typed exactly; a FINAL carries the name and
the time of sign-off and cannot be edited, only replaced by a new run.

A signed pack renders to identical bytes every time: the PDF is built in
reportlab's invariant mode and a FINAL is dated by its sign-off. The SHA-256
recorded when a pack is signed therefore proves which file was signed. The
worked example in `generated/worked_example/` (built by
`scripts/build_worked_example.py` at each release) shows this: its PDF, its
two audit lines, and images of its pages drawn from the file whose hash the
audit records.

---

## How to run

```bash
git clone https://github.com/cfpai0810/board-pack-generator.git
cd board-pack-generator
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
```

### CLI

```bash
python main.py --draft-only       # a DRAFT of the sample with its review notes
python main.py                    # review at the terminal, then sign
```

For your own files, give their paths and say who and when the pack is for:

```bash
python main.py --pnl my_pnl.csv --kpis my_kpis.csv --entity "Test Co" --period "September 2026"
```

Add `--cash-unit pounds` if the KPI file states cash in pounds, and
`--materiality-abs` or `--materiality-pct` to change the thresholds.
`python main.py --help` lists every option.

### Web app

```bash
streamlit run streamlit_app/Home.py
```

The live demo runs on Streamlit Community Cloud from `streamlit_app/Home.py`
with `requirements.txt` and Python 3.13. It needs no secrets.

### API key

The figures, the selection, the template commentary and the sign-off need no
key. Only drafting the commentary with the model needs one.

For the CLI, add your key to a `.env` file at the project root and pass
`--use-model`:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

The key is read from the environment or `.env`, never from a command-line
argument. On the web app, paste it into the sidebar: it is held in the
server's memory for your session only, used to make the call, and never
stored or logged. Only the formatted figures and names in the pack facts are
sent to the model, never your files.

---

## Project structure

```
main.py                          CLI: guided review or --draft-only
config.py                        Layer 1: paths, thresholds, sample entity, model

src/
  state.py                       Shared types: lines, KPIs, sections, flags, the Pack
  step1_load.py                  Layer 2: CSV to typed records, amounts to Decimal
  step2_validate.py              Layer 3: structural checks that warn and carry on
  step3_compute.py               Layer 4: variances, subtotals, margins
  step4_assemble.py              Layer 5: materiality, placement, drivers, sections
  step5_narrate.py               Layer 6: template or model commentary, the checks
  step6_review.py                Layer 7: review, sign-off, the JSONL audit trail
  step7_render.py                Layer 8: the PDF and the rendered audit line
  pipeline.py                    run_pipeline, and the one surface the web app uses
  notes.py                       Every data note, in one plain form
  formatting.py                  Every number as the reader sees it
  tables.py                      The P&L and drivers tables as finished rows
  explain.py                     What the explanation pages quote from a pack

streamlit_app/
  Home.py                        Entry point, landing page, API key gate
  pages/
    1_How_the_pack_is_built.py   The method, for the person who signs
    2_Board_pack.py              The worked example, and a run of your own
    3_Your_own_data.py           The file formats, limits, privacy, running locally
    4_How_its_built.py           The pipeline, tests, audit trail, limitations
  lib/                           Theme, display, inputs, content, key gate

scripts/
  build_worked_example.py        The signed sample pack, its audit lines and page images
  live_smoke.py                  One manual call to the model (never run by the tests)

data/                            The sample P&L and KPI files
generated/                       The worked example and the test counts
tests/                           test_pipeline.py (engine), test_web.py (web app)
output/                          Generated packs and audit logs (gitignored)
```

---

## Audit trail

Every review and every rendered PDF appends one line to an append-only JSONL
file, linked by a run id. The review line records the input files' SHA-256
hashes, the code version, the thresholds, the material items and drivers,
each section's draft and final text, every flag and what was acknowledged at
sign-off, and every data note with its fields. The rendered line records the
PDF's file name and SHA-256.

---

## Test suite

553 tests (475 on the engine, 78 on the web app), with no real API calls:
the model path is tested with fake clients, and the suite blocks every
network connection.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The whole suite runs in GitHub Actions on every push and pull request. A full
passing run writes the counts by area to `generated/test_counts.json`, which
the web app shows.

---

## Limitations

**The checks are soft.** The numeric check reads a figure to the precision it
is written in, so "£3m" raises no flag against the sample's revenue budget of
£2.59m. It catches invented figures, not loose ones: precision is the
reviewer's check.

**KPI direction is unknown.** The KPI file does not say whether higher is
better, so KPI differences are shown as plain differences, not Fav/(Adv).

**One period, pounds only.** Each file holds one month, and every amount is
read as pounds sterling.

**The model adds little.** Once the figures, the selection and the
attribution are computed, the model's wording adds little that the template
does not. That is why the template is the default and the model an option.

---

## Tech stack

Python 3.13 . Anthropic Claude API . Streamlit . reportlab . python-dotenv .
pytest

---

## Related projects

| # | Project | Status |
|---|---------|--------|
| 1 | AI Variance Commentary Engine | Complete |
| 2 | Driver-Based Rolling Forecast Pipeline | Complete |
| 3 | Anomaly Detection and Alert Agent | Complete |
| 4 | NL Scenario Modelling Copilot | Complete |
| 5 | Reconciliation and Tie-Out Assistant | Complete |
| 6 | Board Pack Generator | This project |
| 7 | Planning-to-Warehouse-to-LLM Pipeline | Planned |
| 8 | 13-Week Cash Flow Forecasting Agent | Planned |
| 9 | Multi-Entity Consolidation and FX Engine | Planned |
| 10 | AI Governance Playbook | Planned |
