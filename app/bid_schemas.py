from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class EmploymentType(str, Enum):
    existing = "existing"
    new_hire = "new_hire"


class EmployeeBidInput(BaseModel):
    """Inputs for an employee cost (bid) breakdown.

    CTC is annual. For an existing employee a date of joining is required (it drives
    tenure for PTO and gratuity). For a new hire the date of joining defaults to today.
    """

    name: str = Field(default="Employee", max_length=200)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    ctc: float = Field(..., gt=0, description="Annual cost to company")
    employment_type: EmploymentType = EmploymentType.new_hire
    date_of_joining: date | None = Field(
        default=None, description="Required for existing employees; defaults to today for new hires"
    )
    as_of_date: date | None = Field(
        default=None, description="Reference date for tenure (defaults to today)"
    )
    annual_hours: float = Field(
        default=1880, gt=0, description="Total hours worked per year; used to derive the per-hour rate"
    )
    markup_pct: float = Field(
        default=25, ge=0, description="Markup applied to the grand-total per-hour rate to get the billing rate"
    )

    @model_validator(mode="after")
    def _check_doj(self) -> "EmployeeBidInput":
        if self.employment_type == EmploymentType.existing and self.date_of_joining is None:
            raise ValueError("date_of_joining is required for existing employees")
        return self


class RowKind(str, Enum):
    item = "item"
    subtotal = "subtotal"
    total = "total"


class MoneyRow(BaseModel):
    key: str
    label: str
    monthly: float
    annual: float
    hourly: float
    kind: RowKind = RowKind.item


class EmployeeBidBreakdown(BaseModel):
    name: str
    currency: str
    ctc: float
    employment_type: EmploymentType
    effective_date_of_joining: date
    tenure_years: float
    gratuity_years: int
    pto_days: int
    annual_hours: float
    markup_pct: float
    grand_total_hourly: float
    billing_rate_per_hour: float
    basic_monthly: float
    rows: list[MoneyRow]
