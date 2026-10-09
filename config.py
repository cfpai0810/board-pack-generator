# =============================================================================
# config.py: Layer 1: paths, materiality thresholds, entity metadata
# =============================================================================
"""
Project-level configuration for the Board Pack Generator.

Materiality thresholds TA and TP are module-level constants so they are
trivially made adjustable later (the P5 pattern). Paths resolve relative
to this file so the tool works regardless of working directory.
"""

from decimal import Decimal
from pathlib import Path

# -- Paths (resolve relative to this file, the deploy-safe pattern) -----------

ROOT = Path(__file__).resolve().parent

PNL_PATH = ROOT / "data" / "pnl.csv"
KPIS_PATH = ROOT / "data" / "kpis.csv"
OUTPUT_DIR = ROOT / "output"

# -- Materiality thresholds ---------------------------------------------------
# A variance is material if |abs vBud| >= TA OR |% vBud| >= TP.
# TA is tuned to the sample's revenue scale (~2.5M); a materially different
# scale wants a different TA. TP scales with the company.

MATERIALITY_ABS = Decimal("50000")       # TA: absolute threshold
MATERIALITY_PCT = Decimal("10")          # TP: percentage threshold

# -- Margin display precision -------------------------------------------------

MARGIN_DP = 1                            # gross margin shown to 1 decimal place

# -- Named KPIs ---------------------------------------------------------------
# Matched ignoring case, spaces and punctuation (see Kpi.is_metric).
# Gross margin is derived from the P&L, so a row with this name in kpis.csv
# is ignored with a note: one source for one number. The cash section shows
# the KPI named CASH_KPI_METRIC, in the unit its name states.

GROSS_MARGIN_KPI_METRIC = "Gross margin (%)"
CASH_KPI_METRIC = "Cash balance (GBP 000s)"

# The cash KPI is stated in thousands; prose converts it to pounds before
# formatting, so the raw thousands figure never reaches a sentence.
CASH_KPI_SCALE = 1000

# -- Narrative model (step5, only when a client is injected) ------------------
# Without a client the templated narrative runs; no key is needed. The model
# matches the other live tools in the portfolio (P1 to P4), so a user's key
# behaves the same across the series. No server-side fallback model: if the
# configured model declines or fails, the template is the fallback.

NARRATIVE_MODEL = "claude-sonnet-4-6"
NARRATIVE_EFFORT = "medium"
NARRATIVE_MAX_TOKENS = 16000

# -- Cause-word flag (model prose only) ---------------------------------------
# Phrases that explain a variance rather than attribute it. "came mainly
# from" and "drove" are deliberately absent: naming the lines behind a
# variance is allowed, stating why it happened is the controller's job.

CAUSE_PHRASES = (
    "because", "due to", "owing to", "as a result of", "reflecting",
    "reflects", "caused by", "thanks to", "on the back of",
)

# -- Direction flag (model prose only) ----------------------------------------
# Offset language in a section whose facts list no offsetting line: the
# first live run called a cost overspend an offset. "offsets" is included
# alongside "offset" so the plain verb form is caught too.

DIRECTION_PHRASES = (
    "partially offset", "partly offset", "offsetting", "offsets", "offset",
    "compensated", "cushioned", "mitigated",
)

# -- Code version --------------------------------------------------------------
# Recorded in the audit and on the PDF. The short git commit is used when
# the project is a git repository; otherwise this constant. Bump it whenever
# a change could alter a figure or the narrative from the same inputs.

VERSION = "1.0.0"

# -- The repository -------------------------------------------------------------

REPO_URL = "https://github.com/cfpai0810/board-pack-generator"

# -- Entity and period metadata -----------------------------------------------

ENTITY_NAME = "Harmwell Foods Ltd"
PERIOD = "June 2026"
