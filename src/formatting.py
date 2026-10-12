# =============================================================================
# formatting.py: Shared Helpers: how a figure is written, in prose and tables
# =============================================================================
"""
One place that decides how every figure is written, so the commentary
(step5) and the rendered tables (step7) can never show the same figure two
ways.

Finance reasoning: a board reads prose, not ledgers. Prose money is a
magnitude at a sensible scale (£2.48m, £112k), direction is carried by
words (above budget, below last year, a loss of) rather than minus signs,
and a figure that rounds to nothing reads as nothing ("0.0%", never
"-0.0%"; "in line with budget"). Tables keep whole units. The cash KPI is
stated in thousands or in whole units (the run says which), and is
multiplied out to whole units before it is formatted; a raw thousands
figure never reaches a sentence.

Currency: one per pack, chosen for the run from CURRENCIES; nothing is converted.
Every money helper takes the pack's currency code and writes its
prefix before the number, with commas for thousands: '£2.48m', '€112k',
'CHF 2.48m'. A currency whose sign the PDF's standard fonts cannot print is
written with its ISO code, as CHF is here.

All rounding is ROUND_HALF_UP, the convention a reader expects, applied
only here at display. Every helper takes a Decimal and returns a string.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal


# -- Currency -------------------------------------------------------------------

@dataclass(frozen=True)
class Currency:
    """
    code: the ISO code, 'EUR'. prefix: what is written before an amount,
    '€', or the code and a space for a currency without a printable sign.
    name: the plural for prose, 'euros'.
    """
    code: str
    prefix: str
    name: str

    @property
    def sign(self) -> str:
        """The prefix alone, for a column of a table: '€', 'CHF'."""
        return self.prefix.strip()

    @property
    def label(self) -> str:
        """How a list to choose from shows it: 'EUR (€)', or 'CHF'."""
        return self.code if self.sign == self.code else f"{self.code} ({self.sign})"


CURRENCIES = {c.code: c for c in (
    Currency("GBP", "£", "pounds"),
    Currency("EUR", "€", "euros"),
    Currency("USD", "$", "US dollars"),
    Currency("JPY", "¥", "yen"),
    Currency("CHF", "CHF ", "Swiss francs"),
)}



# -- Rounding -----------------------------------------------------------------

def _round(value: Decimal, places: int) -> Decimal:
    """value rounded half up to places decimal places, minus zero made zero."""
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return rounded.copy_abs() if rounded == 0 else rounded


def is_nil(value: Decimal, places: int = 0) -> bool:
    """True when value rounds to zero at the precision it will be shown."""
    return _round(value, places) == 0


# -- Money --------------------------------------------------------------------

def table_money(value: Decimal) -> str:
    """Whole units with separators for tables: '2,477,550', '-46,120'."""
    return f"{_round(value, 0):,}"


def prose_money(value: Decimal, currency: str) -> str:
    """
    A magnitude for prose in the pack's currency: bn to 2dp at or above 1bn
    ('£1.23bn'), m to 2dp at or above 1m ('£2.48m'), k to the nearest
    thousand at or above 1,000 ('€112k'), whole units below that ('$850',
    'CHF 850'). The unit is chosen after rounding, so 999,600 reads '£1.00m'
    rather than '£1,000k', and 999,996,000 reads '£1.00bn' rather than
    '£1,000.00m'. No sign: the sentence carries the direction.
    """
    prefix = CURRENCIES[currency].prefix
    magnitude = value.copy_abs()
    units = _round(magnitude, 0)
    if units < 1000:
        return f"{prefix}{units}"
    thousands = _round(magnitude.scaleb(-3), 0)
    if thousands < 1000:
        return f"{prefix}{thousands:,}k"
    millions = _round(magnitude.scaleb(-6), 2)
    if millions < 1000:
        return f"{prefix}{millions:,}m"
    return f"{prefix}{_round(magnitude.scaleb(-9), 2):,}bn"


def cash_amount(value: Decimal, scale) -> Decimal:
    """The cash KPI in whole units, given what one unit of it is worth (1000 for thousands, 1 for whole units)."""
    return value * scale


def prose_cash(value: Decimal, scale, currency: str) -> str:
    """Cash KPI figure for prose: 1,176 in thousands, or 1,176,000 in whole units, reads '£1.18m'."""
    return prose_money(cash_amount(value, scale), currency)


def cash_balance_phrase(value: Decimal, scale, currency: str) -> str:
    """
    A cash balance for prose, which may be negative: '£1.18m', or 'an
    overdraft of £120k'. prose_cash gives a magnitude, right for a difference
    ('£174k below target') but not for the balance itself, whose sign the
    sentence must carry, as profit_phrase carries a loss.
    """
    amount = cash_amount(value, scale)
    if amount < 0 and not is_nil(amount):
        return f"an overdraft of {prose_money(amount, currency)}"
    return prose_money(amount, currency)


def profit_phrase(value: Decimal, currency: str, qualifier: str = "") -> str:
    """
    A profit figure that may be negative: 'a loss of £46k', 'a profit of
    £147k', or with qualifier 'budgeted ', 'a budgeted profit of £147k'.
    """
    kind = "loss" if value < 0 and not is_nil(value) else "profit"
    return f"a {qualifier}{kind} of {prose_money(value, currency)}"


# -- Percentages, points and plain numbers ------------------------------------

def pct(value: Decimal, *, signed: bool = False, dp: int = 1) -> str:
    """'4.3%'; signed '-4.3%' or '+14.5%'; anything rounding to zero '0.0%'."""
    rounded = _round(value, dp)
    if not signed or rounded == 0:
        return f"{rounded.copy_abs()}%"
    return f"{rounded:+}%"


def pts(value: Decimal, *, signed: bool = False, dp: int = 1) -> str:
    """Margin points: '4.1 pts'; signed '-4.1 pts'; rounding to zero '0.0 pts'."""
    rounded = _round(value, dp)
    if not signed or rounded == 0:
        return f"{rounded.copy_abs()} pts"
    return f"{rounded:+} pts"


def sign_change(actual: Decimal, comparator: Decimal) -> bool:
    """
    True when actual and comparator have opposite signs (a profit against a
    budgeted loss, or the reverse). A percentage across a change of sign is
    arithmetic, not information: EBIT of -46,120 against 147,000 computes
    to -131.4% but means nothing. Tables print it as n/m, prose leaves it
    out, and the materiality rule applies only its absolute test.
    """
    return (actual < 0 < comparator) or (comparator < 0 < actual)


def table_pct(var_pct, actual: Decimal, comparator: Decimal) -> str:
    """
    A variance % for a table: signed to 1dp ('-4.3%', '+14.5%'), or 'n/m'
    (not meaningful) when the comparator was zero or the sign changed.
    The computed percentage stays stored; only the display changes.
    """
    if var_pct is None or sign_change(actual, comparator):
        return "n/m"
    return pct(var_pct, signed=True)


def number(value: Decimal) -> str:
    """A plain KPI figure as a magnitude: whole numbers as is ('214'), others to 1dp."""
    magnitude = value.copy_abs()
    if magnitude == magnitude.to_integral_value():
        return f"{_round(magnitude, 0):,}"
    return f"{_round(magnitude, 1):,}"


# -- Dates ----------------------------------------------------------------------

def when_text(iso: str) -> str:
    """A UTC timestamp as a person reads it: '9 October 2026 at 08:04 UTC'. The PDF and the screen both use it."""
    dt = datetime.fromisoformat(iso).astimezone(timezone.utc)
    return f"{dt.day} {dt:%B %Y} at {dt:%H:%M} UTC"


# -- Direction words ----------------------------------------------------------

def direction(value: Decimal, against: str, *, places: int = 0) -> str:
    """
    'above budget', 'below budget' or 'in line with budget' for a variance
    of actual minus comparator. The words are the same for every category
    because the variance is raw: a cost overspend is above budget, an
    underspend below it. A variance that rounds to zero at the precision it
    is shown (places) is 'in line with'.
    """
    if is_nil(value, places):
        return f"in line with {against}"
    return f"{'above' if value > 0 else 'below'} {against}"


# -- What the PDF can print ---------------------------------------------------

def unprintable(text: str) -> list[str]:
    """
    Characters in text that the PDF's standard fonts cannot draw (outside
    the Windows-1252 set they encode), once each, in order. step6 flags
    them so the reviewer can fix the text before signing; step7 prints '?'
    only as a last resort.
    """
    found: list[str] = []
    for ch in text:
        if ch in found:
            continue
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            found.append(ch)
    return found


# -- Table cells for the rendered pack (step7) --------------------------------
# The finance reader's conventions. Values: whole units, negatives in
# brackets. Variance columns are Fav/(Adv): favourable plain, adverse in
# brackets, with the percentage following the same sign. For revenue and
# profit the stored variance already reads that way; for costs the sign is
# flipped for display only (an overspend is adverse). Stored values never
# change. Anything that rounds to zero prints without a sign or brackets.

def _bracketed(rounded: Decimal, text: str) -> str:
    return f"({text})" if rounded < 0 else text


def table_value(value: Decimal) -> str:
    """Whole units, negatives in brackets: '1,643,820', '(46,120)', '0'."""
    rounded = _round(value, 0)
    return _bracketed(rounded, f"{rounded.copy_abs():,}")


def fav_adv(variance: Decimal, *, cost: bool) -> str:
    """
    A variance in a Fav/(Adv) column. cost=True flips the stored sign, so
    Marketing's +37,640 overspend shows '(37,640)' and Packaging's -3,030
    underspend shows '3,030'.
    """
    shown = _round(variance.copy_negate() if cost else variance, 0)
    return _bracketed(shown, f"{shown.copy_abs():,}")


def fav_adv_pct(var_pct, actual: Decimal, comparator: Decimal, *, cost: bool) -> str:
    """
    The % beside a Fav/(Adv) variance, same sign treatment: '(4.3%)',
    '0.9%'. 'n/m' when the comparator was zero or the sign changed; '0.0%'
    when it rounds to nothing.
    """
    if var_pct is None or sign_change(actual, comparator):
        return "n/m"
    shown = _round(var_pct.copy_negate() if cost else var_pct, 1)
    return _bracketed(shown, f"{shown.copy_abs()}%")


def margin_cell(value) -> str:
    """Gross margin to 1dp: '35.0%'; 'n/m' when it could not be computed."""
    return "n/m" if value is None else pct(value)


def pts_cell(value) -> str:
    """Margin points to 1dp, Fav/(Adv): '(4.1 pts)', '1.2 pts', '0.0 pts'."""
    if value is None:
        return "n/m"
    shown = _round(value, 1)
    return _bracketed(shown, f"{shown.copy_abs()} pts")


def table_number(value) -> str:
    """A plain KPI figure, negatives in brackets: '214', '(174)', '48.5'; 'n/a' if missing."""
    if value is None:
        return "n/a"
    places = 0 if value == value.to_integral_value() else 1
    rounded = _round(value, places)
    return _bracketed(rounded, f"{rounded.copy_abs():,}")
