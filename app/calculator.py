"""Employee CTC bid breakdown calculation.

All component values are computed monthly first; the annual column is monthly x 12,
except PTO and Gratuity which are computed as annual figures (monthly = annual / 12).

Components
----------
1. Basic            - looked up from the annual CTC slab table (monthly, clamped)
2. HRA              - 50% of Basic
3. Conveyance       - fixed 1,600
4. Medical          - fixed 1,250
5. Employer PF      - based on Basic (two variations around the 15,000 wage ceiling)
6. Special Pay      - balancing figure = CTC/12 - (items 1-5)
   --> Total Earning = sum(1..6) == CTC/12 (monthly), CTC (annual)
7. Paid time-off    - annual; existing employees only; tenure based
8. Gratuity         - annual; Basic x tenure(years) x 15/26
   --> Grand Total  = Total Earning + PTO + Gratuity
"""
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
PF_WAGE_CEILING = 15000.0

# Each tuple is (inclusive upper bound of annual CTC, monthly Basic).
# CTC at or below the first bound -> 15,000; above the last bound -> 42,000.
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
    """Completed years of service with the statutory 6-month rounding rule.

    A trailing period of more than 6 months rounds up to the next year;
    6 months or less is dropped.
    """
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


def calculate_employee_bid(bid: EmployeeBidInput) -> EmployeeBidBreakdown:
    as_of = bid.as_of_date or date.today()

    if bid.employment_type == EmploymentType.existing:
        effective_doj = bid.date_of_joining  # guaranteed by validator
        tenure = tenure_years(effective_doj, as_of)
        gratuity_tenure = gratuity_tenure_years(effective_doj, as_of)
    else:
        # New hires have no service history yet; tenure defaults to 1 year.
        effective_doj = as_of
        tenure = 1.0
        gratuity_tenure = 1

    basic = basic_for_ctc(bid.ctc)
    hra = 0.5 * basic
    conveyance = CONVEYANCE_MONTHLY
    medical = MEDICAL_MONTHLY
    pf = employer_pf(basic)
    monthly_ctc = bid.ctc / 12
    special_pay = monthly_ctc - (basic + hra + conveyance + medical + pf)

    total_earning_monthly = basic + hra + conveyance + medical + pf + special_pay

    # PTO (annual) - tenure based. New hires default to 1 year of tenure -> 15 days.
    pto_days = 20 if tenure > 5 else 15
    pto_annual = (total_earning_monthly / 31) * pto_days

    # Gratuity (annual) - uses completed years with the 6-month rounding rule
    # (existing employees) or the default 1-year tenure for new hires.
    gratuity_annual = basic * gratuity_tenure * (15 / 26)

    grand_total_annual = total_earning_monthly * 12 + pto_annual + gratuity_annual
    annual_hours = bid.annual_hours
    grand_total_hourly = grand_total_annual / annual_hours
    billing_rate_per_hour = grand_total_hourly * (1 + bid.markup_pct / 100)

    def item(key: str, label: str, monthly: float) -> MoneyRow:
        annual = monthly * 12
        return MoneyRow(
            key=key, label=label, monthly=_round(monthly), annual=_round(annual),
            hourly=_round(annual / annual_hours),
        )

    def annual_item(key: str, label: str, annual: float) -> MoneyRow:
        return MoneyRow(
            key=key, label=label, monthly=_round(annual / 12), annual=_round(annual),
            hourly=_round(annual / annual_hours),
        )

    rows = [
        item("basic", "Basic", basic),
        item("hra", "House Rent Allowance (HRA)", hra),
        item("conveyance", "Conveyance Allowance", conveyance),
        item("medical", "Medical Allowance", medical),
        item("employer_pf", "Employer Contribution to PF", pf),
        item("special_pay", "Special Pay", special_pay),
        MoneyRow(
            key="total_earning",
            label="Total Earning",
            monthly=_round(total_earning_monthly),
            annual=_round(total_earning_monthly * 12),
            hourly=_round(total_earning_monthly * 12 / annual_hours),
            kind=RowKind.subtotal,
        ),
        annual_item("pto", "Paid Time-Off", pto_annual),
        annual_item("gratuity", "Gratuity", gratuity_annual),
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
        employment_type=bid.employment_type,
        effective_date_of_joining=effective_doj,
        tenure_years=_round(tenure),
        gratuity_years=gratuity_tenure,
        pto_days=pto_days,
        annual_hours=annual_hours,
        markup_pct=bid.markup_pct,
        grand_total_hourly=_round(grand_total_hourly),
        billing_rate_per_hour=_round(billing_rate_per_hour),
        basic_monthly=_round(basic),
        rows=rows,
    )
