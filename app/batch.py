"""Parse an uploaded batch file and compute a breakdown for each worker.

Expected columns (with or without a header row):
    1) S. No.   2) Name   3) Date of Joining (yyyy-mm-dd)   4) CTC (annual)

Every row is treated as an existing employee, since a date of joining is given.
"""
import csv
import io
import re
from datetime import date, datetime

from openpyxl import load_workbook

from .bid_schemas import (
    BatchError,
    BatchResult,
    BatchRowResult,
    EmployeeBidInput,
    EmploymentType,
)
from .calculator import calculate_employee_bid

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%m/%d/%Y")


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().split(" ")[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_ctc(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _coerce_sno(value):
    if value in (None, ""):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    try:
        f = float(text)
        return int(f) if f.is_integer() else text
    except ValueError:
        return text


def _looks_like_header(cols: list) -> bool:
    doj = cols[2] if len(cols) > 2 else None
    ctc = cols[3] if len(cols) > 3 else None
    return _parse_ctc(ctc) is None and _parse_date(doj) is None


def _rows_from_bytes(filename: str, data: bytes) -> list[list]:
    name = (filename or "").lower()
    if name.endswith((".csv", ".txt")):
        text = data.decode("utf-8-sig", errors="replace")
        return [list(r) for r in csv.reader(io.StringIO(text))]
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.active
    return [list(row) for row in ws.iter_rows(values_only=True)]


def process_batch(filename: str, data: bytes) -> BatchResult:
    raw_rows = _rows_from_bytes(filename, data)
    rows = [r for r in raw_rows if any(c not in (None, "") for c in r)]
    if rows and _looks_like_header(rows[0]):
        rows = rows[1:]

    results: list[BatchRowResult] = []
    errors: list[BatchError] = []

    for i, cols in enumerate(rows, start=1):
        sno = _coerce_sno(cols[0] if len(cols) > 0 else None)
        name = str(cols[1]).strip() if len(cols) > 1 and cols[1] not in (None, "") else ""
        doj = _parse_date(cols[2] if len(cols) > 2 else None)
        ctc = _parse_ctc(cols[3] if len(cols) > 3 else None)

        if not name:
            errors.append(BatchError(row=i, sno=sno, message="Missing name"))
            continue
        if doj is None:
            errors.append(BatchError(
                row=i, sno=sno, name=name,
                message="Invalid or missing Date of Joining (expected yyyy-mm-dd)",
            ))
            continue
        if ctc is None or ctc <= 0:
            errors.append(BatchError(row=i, sno=sno, name=name, message="Invalid or missing CTC"))
            continue

        try:
            bid = EmployeeBidInput(
                name=name,
                ctc=ctc,
                employment_type=EmploymentType.existing,
                date_of_joining=doj,
            )
            breakdown = calculate_employee_bid(bid)
        except Exception as exc:  # noqa: BLE001 - surface row-level failures to the user
            errors.append(BatchError(row=i, sno=sno, name=name, message=str(exc)))
            continue

        results.append(BatchRowResult(sno=sno, breakdown=breakdown))

    return BatchResult(count=len(results), results=results, errors=errors)
