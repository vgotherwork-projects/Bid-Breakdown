import re
from datetime import date

from fastapi import APIRouter, Response

from ..bid_schemas import EmployeeBidBreakdown, EmployeeBidInput
from ..calculator import calculate_employee_bid
from ..exporters import breakdown_to_csv, breakdown_to_pdf

router = APIRouter(prefix="/bids", tags=["bids"])


def _filename(name: str, ext: str) -> str:
    # Mirror the workbook convention: "<Name> Bid Breakdown <Mon D, YYYY>.<ext>".
    clean = re.sub(r'[\\/:*?"<>|]+', " ", name).strip()
    clean = re.sub(r"\s+", " ", clean) or "Employee"
    return f"{clean} Bid Breakdown {date.today():%b %d, %Y}.{ext}"


@router.post("/calculate", response_model=EmployeeBidBreakdown)
def calculate(bid: EmployeeBidInput) -> EmployeeBidBreakdown:
    """Compute an employee CTC cost breakdown (monthly + annual) with PTO and gratuity."""
    return calculate_employee_bid(bid)


@router.post("/export/csv")
def export_csv(bid: EmployeeBidInput) -> Response:
    breakdown = calculate_employee_bid(bid)
    content = breakdown_to_csv(breakdown)
    headers = {"Content-Disposition": f'attachment; filename="{_filename(breakdown.name, "csv")}"'}
    return Response(content=content, media_type="text/csv", headers=headers)


@router.post("/export/pdf")
def export_pdf(bid: EmployeeBidInput) -> Response:
    breakdown = calculate_employee_bid(bid)
    content = breakdown_to_pdf(breakdown)
    headers = {"Content-Disposition": f'attachment; filename="{_filename(breakdown.name, "pdf")}"'}
    return Response(content=content, media_type="application/pdf", headers=headers)
