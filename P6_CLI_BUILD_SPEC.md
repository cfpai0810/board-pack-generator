# Project 6 CLI build spec: Agentic Board Pack Generator

The build order for the CLI core, from the locked PROJECT_6_SCOPE.md. main.py first, seven phases
as tested modules, headless from the start so the web layer reuses the engine, exactly as P5 was
built. This spec says HOW and IN WHAT ORDER, with each phase's acceptance test and the injected
seam. It inherits every standing standard (module structure src/step{N}_, banners, finance-reasoning
docstrings, doc style, sample-data standard, BYO key). House rules: British, no dashes.

The spine: build each phase as a module whose acceptance is a KNOWN sample producing KNOWN numbers.
The compute tie-out (EBIT -46,120, the flagged material set) is P6's acceptance gate, the way
-1381.16 was P5's. Money is Decimal at every boundary via Decimal(str(x)). The pack object is
format-agnostic so render is a thin adapter. The review seam is injected (ask/confirm as
parameters) so CLI and web share one pipeline.

---

## Phase 0: scaffold

  - config.py at root (Layer 1): input paths, the materiality thresholds TA = 50,000 and
    TP = Decimal("10") (percent), entity and period metadata, and the materiality de-dup precedence
    setting. TA and TP are module-level so they are trivially made adjustable later (the P5
    pattern).
  - src/state.py (non-step, Shared Type Definitions): the dataclasses and enums the pipeline passes
    around. At least: PnlLine (line_item, category, actuals, budget, prior_year, plus computed
    variance fields), Kpi (metric, actual, target, prior_year, computed deltas), Section (type,
    title, the figures/tables it holds, a narrative placeholder), Pack (ordered sections, status,
    the material flags, the audit fields). Enums: Category {REVENUE, COGS, OPEX}, SectionType
    {EXEC_SUMMARY, PNL, KPIS, CASH}, PackStatus {DRAFT, FINAL}, and a materiality flag. Money fields
    are Decimal. No step prefix (it is types, not a phase).
  - src/__init__.py empty. Establish the step-file convention now, P6 builds on-convention from the
    first commit (no retrofit, per the standing rule and the P5 lesson).

## Phase 1: step1_load (Layer 2)

Load pnl.csv and kpis.csv into typed records.
  - Coerce all amounts to Decimal via Decimal(str(value)) at the boundary. Accept the formatting
    the portfolio standard requires (currency symbols, thousands separators, parentheses negatives).
  - Validate the category enum: a pnl row whose category is not in {revenue, cogs, opex} is REJECTED
    WITH A NOTE (the P5 report-and-skip discipline), not loaded and not silently coerced.
  - Single-period assumption: one month per file, no period column. If the loader detects what looks
    like multiple periods (a heuristic, or simply document the assumption), it proceeds on the
    single-period contract.
  - Acceptance test: the sample loads to the expected line and KPI counts; every amount is Decimal;
    a row with an unknown category is reported as a problem and not present in the loaded lines; a
    currency-formatted amount parses correctly.

## Phase 2: step2_validate (Layer 3)

Sanity-check the inputs. Warn, never block (the P5 pattern).
  - Every pnl line has a recognised category and a non-blank line_item; the P&L contains at least
    revenue and some costs; every kpi row has an actual.
  - Report problems as warnings the pack can surface; do not halt the pipeline.
  - Acceptance test: the clean sample validates with no warnings; a sample with a blank line_item,
    or a KPI missing its actual, produces the expected warning and still proceeds.

## Phase 3: step3_compute (Layer 4): the deterministic engine, the tie-out gate

Every number in the pack is born here and is tested.
  - Per pnl line: variance vs budget (absolute and %), variance vs prior year (absolute and %).
  - Subtotals COMPUTED from the lines, never taken as given: Revenue (sum of revenue category),
    Gross profit (Revenue minus COGS), Total opex (sum of opex category), EBIT (Gross profit minus
    Total opex). Gross margin % (actual, budget, PY) = Gross profit / Revenue.
  - Per kpi: actual vs target, actual vs PY.
  - All arithmetic in Decimal.
  - THE TIE-OUT GATE (acceptance test, these are the verified sample numbers): Gross profit
    actual 866,390; Total opex 912,510; EBIT -46,120 (against a positive budget of 147,000);
    Gross margin 35.0%; Revenue actual 2,477,550 (vBud -112,450, -4.3%); Gross profit vBud
    -146,610 (-14.5%); Marketing vBud +37,640 (+14.5%); Ingredients vPY +16.0% (the margin-
    compression driver); Export vPY -20.9% (the secondary thread). If the compute does not
    reproduce these exactly, the engine is wrong. Every figure gets a test.

## Phase 4: step4_assemble (Layer 5): the novel phase

Two jobs, no model involved.
  - (a) STRUCTURE: build the Pack as four ordered Sections (exec summary, P&L, KPIs, cash), each
    holding the computed figures/tables it will show and an empty narrative placeholder. Format-
    agnostic. The CASH section is the cash BALANCE summary from the cash KPI (balance vs target vs
    PY), NOT a cash flow statement (the inputs do not support one).
  - (b) MATERIALITY SELECTION: flag each variance where |vBud abs| >= TA OR |vBud %| >= TP.
    DE-DUP RULE (spec it precisely, this is the novel-phase subtlety): a material line and its
    subtotal can both flag. Feature the SUBTOTAL in the exec summary and the underlying LINE in the
    P&L section commentary, so each underlying item is featured once, never both places. On the
    sample the material flag set is {Revenue, Gross profit, EBIT, Marketing, Retail, Export}. The
    de-dup: Retail and Export are material revenue LINES that roll into the material Revenue
    SUBTOTAL, so the exec summary features the subtotals (Revenue, Gross profit, EBIT) plus the
    standalone material opex line (Marketing), and the P&L section commentary covers the material
    revenue lines (Retail, Export). Each underlying item is featured once. Materiality does not
    call the model, it is a rule.
  - Acceptance test: on the sample the material flag set is {Revenue, Gross profit, EBIT,
    Marketing, Retail, Export}; de-dup places the subtotals (Revenue, Gross profit, EBIT) and the
    standalone opex line (Marketing) in the exec-summary feature list, and the material revenue
    lines (Retail, Export) in the P&L commentary list, each underlying item once; the pack has four
    sections in order; no narrative yet; the cash section holds the cash KPI figures, not a cash
    flow.

## Phase 5: step5_narrate (Layer 6): constrained drafting

The model drafts; the numbers are already fixed.
  - Draft the executive summary (a board-altitude synthesis of the exec-summary material items) and
    the per-section variance commentary (explaining the flagged variances).
  - HARD CONSTRAINT: the prompt carries the computed figures for the flagged items and instructs the
    model to explain those figures and introduce no numbers not present. Only figures already in the
    pack.
  - Templated fallback (no key): compose each section's narrative directly from the computed figures,
    guaranteeing a keyless path that cannot invent a number.
  - THE SOFT NUMERIC CHECK: after drafting, scan the narrative for numeric tokens; flag any number
    that corresponds to no computed figure NOR a reasonable rounding of one (2.5M for 2,480,000 is a
    rounding, not a hallucination). It is a FLAG for the human reviewer, not a hard block. Tolerate
    roundings so it is useful not noisy.
  - Acceptance test: the templated fallback produces a narrative for every section using only pack
    figures; the numeric check flags an injected out-of-pack number and passes a legitimate rounding;
    with no key the pipeline still produces a full narrative.

## Phase 6: step6_review (Layer 7): the injected human seam

review(pack, *, ask, confirm, output_dir) -> Pack. This is the headless seam, build it in from the
signature.
  - ask and confirm are INJECTED callables. The CLI passes terminal-prompt implementations; the
    future web layer passes UI-driven ones. The pipeline never imports streamlit and never hardcodes
    a prompt. (This is exactly what let P5's web layer reuse the engine.)
  - The reviewer reads each drafted block, edits or accepts it, and signs off. The pack status is
    DRAFT until sign-off. An intent-confirm gates the transition to FINAL (the number-bearing
    document should not be marked final without an explicit confirm, the P5 intent-confirm pattern).
  - Audit record captures: the inputs, the computed figures, what the model drafted, what the human
    changed, and the sign-off. Written as JSONL (reuse P5's audit pattern).
  - Acceptance test (headless, scripted ask/confirm): a run that signs off flips status to FINAL and
    records the edits; a run that does not confirm stays DRAFT; the audit captures the draft-vs-final
    delta.

## Phase 7: step7_render (Layer 8): parameterised format

render(pack, format="pdf") -> bytes. v1 implements PDF; the format parameter exists from the start.
  - PDF via reportlab, reusing P5's discipline: a status banner (DRAFT / FINAL, filled block), the
    P&L table (actual/budget/PY with variance columns, material items highlighted), the KPI table,
    the cash balance summary, the exec summary and commentary as narrative blocks, a sign-off block,
    and the governance footer. Body numbers not coloured; only status/materiality coding carries
    colour (the P5 restraint).
  - The pack object is format-agnostic, so the PDF renderer reads the Pack and emits bytes. A PPTX
    renderer is a SECOND function over the same Pack object, a v1.1 fast follow. In v1, render
    dispatches on format and the pptx branch is a clearly-marked TODO / raises a not-yet-implemented
    note; the PDF branch is the shipped path.
  - Acceptance test: the PDF builds without error for both DRAFT and FINAL status, is a non-trivial
    size, and contains the computed figures; calling render with format="pptx" behaves as the
    documented v1 stub (does not silently produce a broken file).

## Phase 8: main.py: the CLI orchestrator

  - Orchestrate step1 through step7 in sequence, passing each phase's output to the next.
  - Provide the terminal implementations of ask and confirm for step6.
  - Run on the sample end to end: load, validate, compute, assemble, narrate, review at the terminal,
    render the PDF, write the audit. Reports and outputs to output/ (gitignored).
  - Acceptance: main.py on the sample produces a DRAFT pack whose numbers tie (EBIT -46,120, gross
    margin 35.0%, the flag set {Revenue, Gross profit, EBIT, Marketing, Retail, Export}), a
    templated narrative
    using only pack figures (runs with no key), a sign-off that flips the pack to FINAL, and a PDF
    plus a JSONL audit record.

## Tests

Aim for a real suite (P5 landed at 141). One test class per phase plus edge cases:
  - load: Decimal coercion, unknown-category rejection, formatted amounts, single-period.
  - validate: clean passes, blank line item and missing actual warn.
  - compute: THE tie-out (every verified figure), gross margin, KPI deltas.
  - assemble: the material flag set is {Revenue, Gross profit, EBIT, Marketing, Retail, Export};
    de-dup precedence (subtotals + standalone Marketing to exec summary, Retail/Export to P&L
    commentary); four sections in order; cash is the KPI summary.
  - narrate: templated fallback covers every section using only pack figures; the numeric check
    flags an out-of-pack number and tolerates a rounding; keyless path works.
  - review: sign-off flips to FINAL; no-confirm stays DRAFT; audit captures the delta.
  - render: PDF builds for DRAFT and FINAL, contains the figures; pptx stub behaves as documented.
No real API calls in the suite (templated paths and mocked model, the P5 approach).

## What must hold (carry the P5 discipline)

  - Every number is computed in tested Python; the model never produces or restates a figure.
  - Materiality is the rule, not the model; the de-dup is deterministic.
  - The narrative uses only pack figures; the numeric check surfaces suspected inventions.
  - The review seam is injected, so the web layer reuses this engine unchanged.
  - The pack object is format-agnostic; PDF is v1, PPTX is an additive v1.1 renderer.
  - Read the component numbers, not just the headline: the flagged set and the subtotals are the
    tell that the compute and assemble are right, the way P5's break count was (a passing tie-out
    with the wrong flagged set is still wrong).

## After the CLI core

Once main.py runs the sample end to end with the suite green, the next artefact is the web build
spec (the five-page Streamlit layer wrapping this engine, reusing the foundation and the injected
seam), exactly as P5 went from CLI core to web layer.
