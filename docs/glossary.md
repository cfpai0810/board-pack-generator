# Glossary

One language for the Board Pack Generator, wherever a reader meets it: this
README and docs, the five web pages and the sidebar, the PDF, the data notes
and flags, the CLI's prompts and messages, the model's prompt, and the code's
module banners and docstrings.

A test (`TestGlossary` in `tests/test_pipeline.py`) reads all of that text and
fails if a retired variant comes back. The retired variants are listed beside
each term below.

---

## The product and the document

| Term | Meaning | Retired |
|------|---------|---------|
| Board Pack Generator | The product. | Agentic Board Pack Generator |
| board pack | The document the tool produces. The PDF's subtitle reads "Monthly board pack, June 2026". | management pack |
| DRAFT, FINAL | The pack's two states, always in capitals. A DRAFT carries a watermark and review notes; a FINAL is signed and cannot be edited. | |
| review notes | The last page of a DRAFT: everything outstanding when it was rendered. | |

## What the pack contains

| Term | Meaning | Retired |
|------|---------|---------|
| headline | The sentence that opens page 1: EBIT against budget and last year. Computed. | |
| summary line | The sentence under the headline: how far revenue, COGS and opex moved against budget, and how revenue and the gross margin compare with last year. Computed. | standfirst |
| tiles | The four figures under the summary line: revenue, gross profit, the gross margin and EBIT, each against budget and last year. Computed. | |
| commentary | The written sections: the executive summary, the commentary on material lines, the KPIs and cash. Drafted by the template or the model, then edited by the reviewer. | narrative |
| the budget-to-actual bridge | The chart that steps from budget EBIT to actual EBIT through revenue, COGS and opex. | EBIT walk, EBIT bridge |
| drivers | The lines whose budget variances moved a material profit subtotal most, each as its effect on profit, in a computed table. | |
| P&L message | The sentence that opens the P&L page. Computed. | |
| data notes | The messages about the input files from loading and validation, and from drafting when the model's reply could not be used. | warnings (for these messages) |

The headline, the summary line, the tiles, the charts and the P&L message are
computed from the figures. The reviewer cannot edit them, and the numeric
check runs on them in the tests.

## Judgements and checks

| Term | Meaning | Retired |
|------|---------|---------|
| material | Only for an item the materiality rule selects: a variance against budget at or above either threshold. | flagged as material, material flag |
| flag | Only for what the four checks raise: numeric, cause, direction and glyph. A flag never blocks. | |
| Fav/(Adv) | The heading of a variance column: favourable plain, adverse in brackets. Written exactly so. | Fav/Adv, F/(A) |
| n/m | Not meaningful: a percentage over a zero comparator or across a change of sign. Written exactly so. | N/M, n.m. |

## People and drafters

| Term | Meaning | Retired |
|------|---------|---------|
| the reviewer | The person who reads the pack, edits the commentary and signs. The worked example's reviewer is a sample name, A. Controller. | controller, the person who signs, signatory, approver, preparer |
| the model | Claude, via the Anthropic API, which drafts the commentary when a key is given. The first mention on each page or document says so: "the model (Claude, via the Anthropic API)". Its id comes from `config.py` (`NARRATIVE_MODEL`) and is never typed anywhere else. | the AI, AI layer, LLM, language model |
| the template | The default drafter: code that writes the commentary from the same facts, the same way every time, with no key. | |

## Comparisons

Table headers say "Budget" and "Prior year"; prose says "budget" and "last
year". So the P&L table has a "Prior year" column and a "Fav/(Adv) vs prior
year" group, while a sentence reads "£128k (5.5%) above last year". The input
files' column is named `prior_year`.

## Currency

One currency per pack, chosen for the run: GBP (£), EUR (€), USD ($), JPY (¥)
or CHF. Every amount is written in it, the sign before the number and commas
for thousands: "€2.48m", "(€112k)", "CHF 2.48m". A currency whose sign the
PDF's standard fonts cannot print is written with its ISO code, as CHF is.
Nothing is converted. In prose the currency's name is plural: "stated in
euros". The cash KPI is stated in "thousands" or "whole units", and the note
under the cash table says how it is shown: "Shown in whole Swiss francs; the
KPI file states cash in thousands."

"Converted" is retired in every form, so a reader never takes a change of
unit for a change of currency. It appears only as "nothing is converted".

Retired: "pounds sterling only", "pounds only", "treated as pounds" and "a
pound sign" for amounts in general. Pounds are named only for the Harmwell
sample, which is in GBP. The command line still accepts `--cash-unit
pounds`, published before v1.2.0, as `--cash-unit units`, with a note.

## Figures

Table labels are "Revenue", "COGS", "Opex", "EBIT", "Gross profit" and
"Gross margin". In prose they are revenue, COGS, opex, EBIT, gross profit and
the gross margin: "the revenue subtotal", never "the Revenue subtotal". A
line's own name keeps its capitals, in quotes when a note cites it.

## Sign-off

| Term | Meaning |
|------|---------|
| SIGN | The word typed, exactly, to sign off. |
| sign-off | The noun: "the time of sign-off". |
| sign off | The verb: "the reviewer signs off the pack". |
