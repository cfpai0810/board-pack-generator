# Project 6 scope: Board Pack Generator

First full scope, built from the confirmed first-pass decisions. This is the document the engineer
would build a CLI from, in the same shape as PROJECT_5_SCOPE. It inherits every standing standard
already in the master plan: the three-product architecture (Streamlit web, GitHub package,
content), the governance model, the module-structure convention (src/step{N}_ files, banners,
finance-reasoning docstrings), the documentation-style standard, the sample-data standard, and
bring-your-own-key. House rules: British, no dashes.

---

## 1. What it is, and why it is distinct

The Board Pack Generator assembles a monthly management pack from the underlying numbers:
the deterministic figures produced by code, and the narrative drafted by the model for human
review. v1 is a management pack with a board-ready executive summary layered on top, the same
computed numbers narrated up a level.

Its distinct identity in the portfolio: P1 to P5 each PERFORM ONE ANALYSIS (variance commentary,
forecast, anomaly detection, scenario modelling, reconciliation). P6 is the first project whose
primary value is ASSEMBLY, composing a multi-section deliverable from several underlying
computations. The novel phase is step4_assemble (structure the pack, select what is material,
slot the computed numbers in, before any narrative). Nothing in P1 to P5 had a document-assembly
step; that is P6's contribution.

It is also the portfolio's strongest governance story, and the scope should front this. A board
pack is the artifact where "AI wrote it" is scariest, because the board makes decisions off it.
P6's answer is the whole thesis in one place: what is MATERIAL is computed by a rule (not the
model's judgement), every NUMBER is born in tested Python (the model never produces a figure), the
model drafts only the NARRATIVE and only from figures already in the pack, and a HUMAN signs off
before it is a pack rather than a draft. This is the P1 lesson (separate calculation from
commentary) at document scale.

## 2. The governance model applied to P6

  - Every number in the pack is computed deterministically in step3 from the source data and is
    tested. The model is never asked to produce, restate, or adjust a figure.
  - Materiality (which variances are worth featuring) is a DETERMINISTIC RULE in step4, not a
    model decision. WHAT is material is computed; HOW it is explained is drafted. This line is the
    heart of P6's governance and must be explicit in the build.
  - The model drafts the narrative in step5 constrained to the figures already computed and
    present in the pack. The prompt carries the computed numbers and instructs the model to
    explain them and introduce no new numbers. A templated fallback runs without a key.
  - The pack is a DRAFT until a human reviews the narrative and signs off (step6). An intent
    confirm gates the transition to final. The audit trail records the inputs, the computed
    figures, what the model drafted, what the human changed, and the sign-off.

## 3. The inputs (two files)

Two CSVs, mirroring P5's two-file clarity:
  - pnl.csv: the profit-and-loss lines. Columns: line_item, category, actuals, budget,
    prior_year. category is an ENUM, one of {revenue, cogs, opex}, used to compute the subtotals.
    Because the recognised categories are revenue, cogs, and opex, v1 computes to EBIT, NOT net
    income (there are no tax, interest, or depreciation lines below EBIT in v1). A row whose
    category is not one of the three is rejected with a note (the P5 report-and-skip discipline),
    not silently mishandled. One row per account line. The input is SINGLE-PERIOD: one month per
    file, there is no period column, so a file must contain exactly one period's P&L.
  - kpis.csv: the operational and cash metrics. Columns: metric, actual, target, prior_year
    (prior_year optional). One row per KPI (headcount, cash balance, DSO, etc.).
The loader accepts the same formatting tolerance the portfolio standard requires (currency
symbols, thousands separators, parentheses negatives, the date and encoding handling from P5's
load hardening where relevant). Amounts are Decimal at the boundary, as in P5.

## 4. The seven phases

  step1_load     Load pnl.csv and kpis.csv into typed records. Coerce amounts to Decimal. Report
                 unparseable rows as problems, never silently drop (the P5 report-and-skip
                 discipline).
  step2_validate Check the inputs make sense: categories are recognised, no blank line items, the
                 P&L has at least revenue and some costs, KPI rows have an actual. Warn, do not
                 block (P5 pattern).
  step3_compute  The deterministic engine. Every number in the pack is born here and is tested:
                   - per line: variance vs budget (absolute and %), variance vs prior year
                   - subtotals COMPUTED from the lines, not taken as given: revenue, gross profit
                     (revenue minus cogs), total opex, EBIT (gross profit minus opex)
                   - gross margin % (actual, budget, PY)
                   - per KPI: actual vs target, actual vs PY
                 Subtotals are computed so the pack's arithmetic is the tool's and is verifiable.
  step4_assemble THE NOVEL PHASE. Two jobs:
                   (a) STRUCTURE: build the ordered pack as typed section objects (exec summary,
                       P&L, KPIs, cash), each holding the computed figures/tables it will show and
                       a placeholder for its narrative. Format-agnostic (see step7). NOTE on the
                       cash section: the inputs are a P&L and a KPI file, and cash is not derivable
                       from a P&L (profit is not cash). So v1's cash section is the cash BALANCE
                       summary drawn from the cash KPI in kpis.csv (balance vs target vs prior
                       year), NOT a cash flow statement. A real cash flow statement would need
                       opening/closing/movement inputs the tool does not take in v1. Do not
                       document or render more cash detail than the inputs can fill.
                   (b) MATERIALITY SELECTION: apply the deterministic materiality rule to flag the
                       variances worth featuring. These flags drive what the exec summary features
                       and what the model is asked to explain. The model does NOT run here.
                 Output: the pack skeleton with computed numbers slotted in and material items
                 flagged, no narrative yet.
  step5_narrate  The model drafts, constrained to figures in the pack:
                   (a) the executive summary, a board-altitude synthesis of the flagged material
                       items (the revenue miss, the margin compression, the opex overrun, the EBIT
                       impact)
                   (b) per-section variance commentary explaining the flagged variances
                 Hard constraint: only figures already computed and present in the pack; introduce
                 no new numbers. Templated fallback without a key. Everything drafted is a DRAFT.
  step6_review   Human review and sign-off. The controller reads each drafted block, edits or
                 accepts, and signs off. Until sign-off the pack status is DRAFT. Intent-confirm
                 before final. Audit record captures inputs, computed figures, model drafts, human
                 edits, sign-off. (Reuse P5's resolve/sign-off/audit pattern directly.)
  step7_render   render(pack, format). v1 implements PDF; the pack object is format-agnostic so a
                 PPTX renderer is a second function over the same object (see section 8). The PDF
                 reuses P5's reportlab discipline: a status banner (DRAFT / FINAL), the P&L table
                 with actual/budget/PY and variance columns (material items highlighted), the KPI
                 table, the cash summary, the exec summary and commentary as narrative blocks, a
                 sign-off block, and the governance footer. Plus the JSONL audit trail.

Non-step modules per the convention: config.py at root (Layer 1: paths, the materiality
thresholds, entity/period metadata), src/state.py (the pack and section dataclasses, enums).

## 5. The materiality rule (the deterministic selection)

A variance is material if the absolute variance vs budget is at least a threshold OR the
percentage variance vs budget is at least a threshold: |abs vBud| >= TA or |% vBud| >= TP.
Defaults in config (proposed): TA = 50,000, TP = 10%. These are adjustable in config now and are
a natural candidate for a user-facing control later (the way P5's tolerance became adjustable);
v1 can ship them config-only and note the UI control as a fast follow.
SCALE NOTE (this is the P5-tolerance situation, name it): the percentage arm (TP) scales with the
company,
but the ABSOLUTE arm (TA) is scale-bound, 50,000 is about 2% of revenue for the sample company but
is too loose for a much smaller company and too tight for a much larger one, exactly the problem
P5's absolute tolerance had. For v1 the fixed defaults are tuned to the sample's scale and are
fine config-only, but the honest v1.1 is user-adjustable TA and TP, and P5 already built precisely
this pattern (adjustable absolute plus relative thresholds, frozen-default, provenance-recorded),
so P6 can inherit it cheaply rather than reinventing it. Document TA as tuned for the sample's
revenue scale; a materially different scale wants a different TA.
DE-DUP DETAIL for the build: a line and its subtotal can both flag (for example Revenue as a line
and Revenue as a total). step4 must de-duplicate so the same item is featured once, and must
decide precedence when a subtotal and its components both flag (feature the subtotal in the exec
summary, the components in the P&L commentary). Flag this explicitly so it is handled, not
discovered.

## 6. The narrative constraint (the load-bearing governance mechanism)

This is more load-bearing in P6 than in P5, because the narrative is longer and has more places to
invent a number. The mechanism:
  - the step5 prompt includes the computed figures for the flagged items and the pack context, and
    instructs the model to explain those figures and introduce no numbers not present
  - the templated fallback composes the narrative from the computed figures directly (no model),
    guaranteeing a keyless path that cannot invent anything
  - a light post-check is worth specifying: the drafted narrative should not contain numeric
    tokens absent from the computed set (a soft check that flags a possible hallucinated figure
    for the human reviewer, not a hard block). This is a governance feature, surface a suspected
    invented number rather than trust the prose. REFINEMENT: the check must tolerate REASONABLE
    ROUNDINGS of the computed figures, "2.5M" for 2,477,550 is a rounding, not a hallucination, so
    the check flags only numbers that correspond to no computed figure NOR a reasonable rounding of
    one. Otherwise it cries wolf on legitimate rounded phrasing and the reviewer learns to ignore
    it, which defeats the purpose.

## 7. The sample data (designed, tie-out verified)

The sample is Harmwell Foods Ltd, a small maker of chilled ready meals and soups selling to
retail, food service, and export, monthly management pack, June 2026. The P&L is a realistic
multi-line structure (three revenue lines, three COGS lines, five opex lines) with messy actual
figures (actuals are odd pounds, as real actuals are; budgets are roundish planning numbers; prior
year is a real historical actual, so also messy). It is designed so the pack has a genuine story to
tell, not "all on budget". These are the shipped figures (the CSV files carry exactly these; the
build spec's tie-out gate carries the same numbers, one source of truth). Verified from the parsed
CSV, subtotals compute and variances tie:

  P&L lines (actual / budget / prior year), category in brackets:
    Retail            [revenue]  1,643,820 / 1,700,000 / 1,521,440
    Food service      [revenue]    612,540 /   640,000 /   548,210
    Export            [revenue]    221,190 /   250,000 /   279,630   (down 20.9% vs PY)
    Ingredients       [cogs]       942,310 /   905,000 /   812,470   (up 16.0% vs PY, the margin driver)
    Packaging         [cogs]       318,970 /   322,000 /   296,180
    Production labour [cogs]       349,880 /   350,000 /   331,920
    Marketing         [opex]       297,640 /   260,000 /   241,880   (over budget 14.5%)
    Personnel         [opex]       356,210 /   352,000 /   329,740
    Logistics         [opex]       141,560 /   138,000 /   127,310
    Facilities        [opex]        64,720 /    66,000 /    61,050
    IT and admin      [opex]        52,380 /    50,000 /    47,920
  Computed subtotals (actual / budget / prior year):
    Revenue              2,477,550 / 2,590,000 / 2,349,280   (vBud -112,450, -4.3%)
    Gross profit           866,390 / 1,013,000 /   908,710   (vBud -146,610, -14.5%)
    Total opex             912,510 /   866,000 /   807,900   (vBud +46,510, +5.4%)
    EBIT                   -46,120 /   147,000 /   100,810   (vBud -193,120; a loss vs a positive budget)
    Gross margin              35.0% /     39.1% /     38.7%   (vs budget -4.1pts, vs PY -3.7pts; shown to 1dp)
  KPIs (actual / target / prior year):
    Headcount 214 / 205 / 198     Cash balance (GBP 000s) 1,176 / 1,350 / 1,288
    DSO (days) 48 / 42 / 45        Gross margin (%) 35 / 39 / 39

The story: revenue modestly below budget across all three channels, gross margin compressed vs
both budget and prior year (Ingredients up 16% vs PY, a real input-cost story visible in the line,
not just the aggregate), marketing overspent, EBIT swinging to a small loss against a positive
budget. A secondary thread: Export down 21% vs prior year. The KPIs reinforce it: headcount over
plan (ties to Personnel), cash below target (ties to the weaker EBIT), DSO stretched. At the
thresholds (TA 50,000, TP 10%) the materiality rule flags the set {Revenue, Gross profit, EBIT,
Marketing, Retail, Export}. The de-dup then features the subtotals (Revenue, Gross profit, EBIT)
plus the standalone material opex line (Marketing) in the exec summary, and the material revenue
lines (Retail, Export) in the P&L commentary, so each underlying item is featured once. Gross
margin is displayed to ONE decimal place (35.0%, not 34.97%), the management-pack convention.
The engineer must reproduce these figures (subtotals from the lines, variances, the flag set) as
the compute and assemble tie-out, the way P5's -1381.16 was the acceptance figure.
A second BYO-style sample (a different small company, a cleaner or a messier month) is the
bring-your-own-data deliverable, per the standard.

## 8. Render: PDF first, PPTX parameterised

render(pack, format="pdf") ships in v1. The pack object built by step4 and filled by step5/step6
is FORMAT-AGNOSTIC (sections, figures, tables, narrative blocks, status), so:
  - the PDF renderer (reportlab, reusing P5's discipline) is the v1 deliverable
  - a PPTX renderer (python-pptx) is a second function over the SAME pack object, a fast follow,
    not a re-architecture
Design step7 with format as a parameter from the start so "configurable" is built in, not
retrofitted. v1 acceptance is a clean PDF; PPTX is explicitly a v1.1 deliverable so the v1
boundary holds.

## 9. Web layer (thin presentation, five pages)

The same five-page Streamlit shape as P1 to P5, reusing the foundation (theme, key_gate,
claude_client, audit, errors):
  - Home: landing + key gate
  - How the Model Works: plain-language explanation (the compute/materiality/narrate/review split)
  - The Board Pack tool: the star page. On sample data (no upload): show the computed pack, the
    material flags, the drafted narrative (key-gated AI, templated fallback keyless), the
    review/edit/sign-off, and the PDF download. The assembly and the material flagging are visible,
    so a viewer sees WHAT was computed vs WHAT was drafted.
  - Your Own Data: the two-file schema, accepted formats, run commands, the key-cost note, honest
    limits, privacy.
  - How Its Built: the technical and governance detail, the three-diagram set.

## 10. What makes P6 harder than P5 (honest risks, name them in the build)

  - Multi-section assembly is more moving parts than a single reconciliation; step4 is genuinely
    new and needs the clearest spec and tests.
  - The narrative is longer with more room to invent a number; the "only figures in the pack"
    constraint plus the soft numeric check is more load-bearing here.
  - A board pack LOOKS polished, so the PDF layout bar is higher than P5's single-statement PDF; a
    multi-section pack is more layout work.
  - Scope creep: "board pack" wants to grow (balance sheet, risks, forecast, more KPIs). The
    four-section v1 boundary (exec summary, P&L, KPIs, cash) must hold; additions are v1.1+.

## 11. Open questions for the CLI build spec (all CONFIRMED)

All five are confirmed, each with the clarification now folded into the sections above.
  1. CONFIRMED. Two-file input schema (pnl.csv line_item/category/actuals/budget/prior_year;
     kpis.csv metric/actual/target/prior_year). Clarified in Section 3: category is an enum
     {revenue, cogs, opex}, the pack computes to EBIT not net income, unrecognised categories are
     rejected with a note, and the input is single-period (one month per file).
  2. CONFIRMED. Materiality thresholds TA 50,000 / TP 10% as v1 defaults, config-only. Clarified
     in Section 5: this is the P5-tolerance situation, the absolute arm is scale-bound, the
     defaults are tuned to the sample's scale, and user-adjustable TA/TP inheriting P5's pattern
     is the v1.1 fast follow.
  3. CONFIRMED. Four-section boundary (exec summary, P&L, KPIs, cash) for v1. Clarified in
     Section 4: the cash section is the cash BALANCE summary from the cash KPI, NOT a cash flow
     statement (the inputs do not support a cash flow); no balance sheet, risks, or forecast in v1.
  4. CONFIRMED. PDF-only for v1, PPTX as v1.1, format parameterised from the start (Section 8).
  5. CONFIRMED. The soft numeric check is a flag-for-review, not a hard block. Clarified in
     Section 6: it tolerates reasonable roundings of computed figures, so it flags only numbers
     with no computed correspondent, useful rather than noisy.
The scope is locked. The next artefact is the CLI build spec (P6_CLI_BUILD_SPEC.md), main.py
first, seven phases, headless from the start, built on this scope, exactly as P5 was.

---

## What this project proves

P6 is close to the thesis project for the whole portfolio. It takes the artifact where AI in
finance is most dangerous, the document a board makes decisions from, and makes it safe by the
same discipline as everything else: the numbers are computed and tested, materiality is a rule not
a guess, the model writes only prose and only from those numbers, and a human signs off before it
counts. It is the board-decks story from the Intro 3 post, built.
