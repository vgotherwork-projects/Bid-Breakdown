import re
from datetime import date

from fastapi import APIRouter, File, Response, UploadFile

from ..batch import process_batch
from ..bid_schemas import BatchResult, EmployeeBidBreakdown, EmployeeBidInput
from ..calculator import calculate_employee_bid
from ..exporters import batch_to_xlsx, breakdown_to_pdf, breakdown_to_xlsx

router = APIRouter(prefix="/bids", tags=["bids"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _filename(name: str, ext: str) -> str:
    # Naming convention: "<Employee Name>_Bid Breakdown_<Mon D, YYYY>.<ext>".
    clean = re.sub(r'[\\/:*?"<>|]+', " ", name).strip()
    clean = re.sub(r"\s+", " ", clean) or "Employee"
    return f"{clean}_Bid Breakdown_{date.today():%b %d, %Y}.{ext}"


@router.post("/calculate", response_model=EmployeeBidBreakdown)
def calculate(bid: EmployeeBidInput) -> EmployeeBidBreakdown:
    """Compute an employee CTC cost breakdown (monthly + annual) with PTO and gratuity."""
    return calculate_employee_bid(bid)


@router.post("/export/xlsx")
def export_xlsx(bid: EmployeeBidInput) -> Response:
    breakdown = calculate_employee_bid(bid)
    content = breakdown_to_xlsx(breakdown)
    headers = {"Content-Disposition": f'attachment; filename="{_filename(breakdown.name, "xlsx")}"'}
    return Response(content=content, media_type=XLSX_MEDIA_TYPE, headers=headers)


@router.post("/export/pdf")
def export_pdf(bid: EmployeeBidInput) -> Response:
    breakdown = calculate_employee_bid(bid)
    content = breakdown_to_pdf(breakdown)
    headers = {"Content-Disposition": f'attachment; filename="{_filename(breakdown.name, "pdf")}"'}
    return Response(content=content, media_type="application/pdf", headers=headers)


@router.post("/batch/calculate", response_model=BatchResult)
async def batch_calculate(file: UploadFile = File(...)) -> BatchResult:
    """Parse an uploaded file (S.No, Name, DOJ, CTC) and compute every breakdown."""
    data = await file.read()
    return process_batch(file.filename or "", data)


@router.post("/batch/export")
async def batch_export(file: UploadFile = File(...)) -> Response:
    """Return one wide master sheet: a row per worker, components across columns."""
    data = await file.read()
    result = process_batch(file.filename or "", data)
    content = batch_to_xlsx(result.results)
    headers = {"Content-Disposition": f'attachment; filename="{_filename("Batch", "xlsx")}"'}
    return Response(content=content, media_type=XLSX_MEDIA_TYPE, headers=headers)
