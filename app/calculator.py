"""Employee CTC bid breakdown calculation.

All component values are computed monthly first; the annual column is monthly x 12,
except PTO and Gratuity which are computed as annual figures (monthly = annual / 12).

Components
----------
1. Basic            - looked up from the annual CTC slab table (monthly, clamped)
2. HRA              - 50% of Basic
3. Conveyance       - fixed 1,600
4. Medical          - fixed 1,250
5. Employer PF      - based on Basic (two variations around the 25,000 wage ceiling)
6. Special Pay      - balancing figure = CTC/12 - (items 1-5)
   --> Total Earning = sum(1..6) == CTC/12 (monthly), CTC (annual)
7. Paid time-off / leave encashment - annual; tenure based (formula)
   Optional proportionality vs reference CTC adjusts leave encashment so
   grand-total per hour scales with CTC / reference CTC.
8. Gratuity         - annual; Basic x tenure(years) x 15/26
   --> Grand Total  = Total Earning + Adjusted leave encashment + Gratuity
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .bid_schemas import (
    EmployeeBidBreakdown,
    EmployeeBidInput,
    EmploymentType,
    MoneyRow,
    RowKind,
)

CONVEYANCE_MONTHLY = 1600.0
MEDICAL_MONTHLY = 1250.0
PF_WAGE_CEILING = 25000.0

BASIC_SLABS: list[tuple[float, float]] = [
    (350000, 15000.0),
    (630000, 15000.0),
    (812400, 18030.0),
    (1003200, 22695.0),
    (1203840, 27588.0),
    (1440000, 33000.0),
    (1920000, 42000.0),
]
BASIC_ABOVE_TOP = 42000.0
DAYS_PER_YEAR = 365.25


def _round(value: float) -> float:
    return round(value + 0.0, 2)


def basic_for_ctc(ctc: float) -> float:
    for upper, basic in BASIC_SLABS:
        if ctc <= upper:
            return basic
    return BASIC_ABOVE_TOP


def employer_pf(basic_monthly: float) -> float:
    if basic_monthly >= PF_WAGE_CEILING:
        return basic_monthly * 0.12 + basic_monthly * 0.005 + PF_WAGE_CEILING * 0.005
    return basic_monthly * 0.12 + basic_monthly * 0.005 + basic_monthly * 0.005


def tenure_years(date_of_joining: date, as_of: date) -> float:
    return max((as_of - date_of_joining).days, 0) / DAYS_PER_YEAR


def gratuity_tenure_years(date_of_joining: date, as_of: date) -> int:
    """Completed years of service with the statutory 6-month rounding rule."""
    years = as_of.year - date_of_joining.year
    months = as_of.month - date_of_joining.month
    days = as_of.day - date_of_joining.day
    if days < 0:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    if years < 0:
        return 0
    if months > 6:
        years += 1
    return years


@dataclass
class _TenureContext:
    effective_doj: date
    tenure: float
    gratuity_tenure: int
    pto_days: int


def _tenure_context(bid: EmployeeBidInput, as_of: date) -> _TenureContext:
    if bid.employment_type == EmploymentType.existing:
        effective_doj = bid.date_of_joining  # type: ignore[assignment]
        tenure = tenure_years(effective_doj, as_of)
        gratuity_tenure = max(gratuity_tenure_years(effective_doj, as_of), 1)
    else:
        effective_doj = as_of
        tenure = 1.0
        gratuity_tenure = 1
    pto_days = 20 if tenure > 5 else 15
    return _TenureContext(effective_doj, tenure, gratuity_tenure, pto_days)


@dataclass
class _CoreAmounts:
    ctc: float
    basic: float
    hra: float
    conveyance: float
    medical: float
    pf: float
    special_pay: float
    total_earning_monthly: float
    gratuity_annual: float
    leave_encashment_original_annual: float
    grand_total_annual_with_original_leave: float


def _compute_core(bid: EmployeeBidInput, ctc: float, ctx: _TenureContext) -> _CoreAmounts:
    basic = basic_for_ctc(ctc)
    hra = 0.5 * basic
    conveyance = CONVEYANCE_MONTHLY
    medical = MEDICAL_MONTHLY
    pf = employer_pf(basic)
    monthly_ctc = ctc / 12
    special_pay = monthly_ctc - (basic + hra + conveyance + medical + pf)
    total_earning_monthly = basic + hra + conveyance + medical + pf + special_pay
    leave_original = (total_earning_monthly / 31) * ctx.pto_days
    gratuity_annual = basic * ctx.gratuity_tenure * (15 / 26)
    grand_with_original = ctc + leave_original + gratuity_annual
    return _CoreAmounts(
        ctc=ctc,
        basic=basic,
        hra=hra,
        conveyance=conveyance,
        medical=medical,
        pf=pf,
        special_pay=special_pay,
        total_earning_monthly=total_earning_monthly,
        gratuity_annual=gratuity_annual,
        leave_encashment_original_annual=leave_original,
        grand_total_annual_with_original_leave=grand_with_original,
    )


def _adjusted_leave_encashment(
    bid: EmployeeBidInput,
    core: _CoreAmounts,
    ref_core: _CoreAmounts | None,
) -> float:
    if ref_core is None:
        return core.leave_encashment_original_annual
    # Target grand total scales with CTC vs reference so cost/hour moves proportionally.
    ratio = core.ctc / ref_core.ctc
    target_grand = ref_core.grand_total_annual_with_original_leave * ratio
    adjusted = target_grand - core.ctc - core.gratuity_annual
    return max(adjusted, 0.0)


def calculate_employee_bid(bid: EmployeeBidInput) -> EmployeeBidBreakdown:
    as_of = bid.as_of_date or date.today()
    ctx = _tenure_context(bid, as_of)
    core = _compute_core(bid, bid.ctc, ctx)

    ref_ctc = bid.reference_ctc
    ref_core: _CoreAmounts | None = None
    if ref_ctc is not None and ref_ctc > 0 and abs(ref_ctc - bid.ctc) > 0.009:
        ref_core = _compute_core(bid, ref_ctc, ctx)

    leave_original = core.leave_encashment_original_annual
    leave_adjusted = _adjusted_leave_encashment(bid, core, ref_core)

    grand_total_annual = core.ctc + leave_adjusted + core.gratuity_annual
    annual_hours = bid.annual_hours
    grand_total_hourly = grand_total_annual / annual_hours
    billing_rate_per_hour = grand_total_hourly * (1 + bid.markup_pct / 100)

    def item(key: str, label: str, monthly: float) -> MoneyRow:
        annual = monthly * 12
        return MoneyRow(
            key=key,
            label=label,
            monthly=_round(monthly),
            annual=_round(annual),
            hourly=_round(annual / annual_hours),
        )

    def annual_item(key: str, label: str, annual: float) -> MoneyRow:
        return MoneyRow(
            key=key,
            label=label,
            monthly=_round(annual / 12),
            annual=_round(annual),
            hourly=_round(annual / annual_hours),
        )

    pto_label = (
        "Leave encashment (Paid Time-Off)"
        if abs(leave_adjusted - leave_original) > 0.009
        else "Paid Time-Off"
    )

    rows = [
        item("basic", "Basic", core.basic),
        item("hra", "House Rent Allowance (HRA)", core.hra),
        item("conveyance", "Conveyance Allowance", core.conveyance),
        item("medical", "Medical Allowance", core.medical),
        item("employer_pf", "Employer Contribution to PF", core.pf),
        item("special_pay", "Special Pay", core.special_pay),
        MoneyRow(
            key="total_earning",
            label="Total Earning",
            monthly=_round(core.total_earning_monthly),
            annual=_round(core.ctc),
            hourly=_round(core.ctc / annual_hours),
            kind=RowKind.subtotal,
        ),
        annual_item("pto", pto_label, leave_adjusted),
        annual_item("gratuity", "Gratuity", core.gratuity_annual),
        MoneyRow(
            key="grand_total",
            label="Grand Total",
            monthly=_round(grand_total_annual / 12),
            annual=_round(grand_total_annual),
            hourly=_round(grand_total_annual / annual_hours),
            kind=RowKind.total,
        ),
    ]

    return EmployeeBidBreakdown(
        name=bid.name,
        currency=bid.currency,
        ctc=bid.ctc,
        reference_ctc=ref_ctc if ref_core is not None else None,
        leave_encashment_original_annual=_round(leave_original),
        leave_encashment_adjusted_annual=_round(leave_adjusted),
        employment_type=bid.employment_type,
        effective_date_of_joining=ctx.effective_doj,
        tenure_years=_round(ctx.tenure),
        gratuity_years=ctx.gratuity_tenure,
        pto_days=ctx.pto_days,
        annual_hours=annual_hours,
        markup_pct=bid.markup_pct,
        grand_total_hourly=_round(grand_total_hourly),
        billing_rate_per_hour=_round(billing_rate_per_hour),
        basic_monthly=_round(core.basic),
        rows=rows,
    )