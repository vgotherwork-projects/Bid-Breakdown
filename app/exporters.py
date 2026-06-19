"""CSV and PDF renderers for an employee bid breakdown."""
import csv
import io
from functools import lru_cache
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageChops

from .bid_schemas import EmployeeBidBreakdown, EmploymentType

LOGO_PATH = Path(__file__).resolve().parent / "static" / "logo.png"

# Pixels whose strongest channel is below this are treated as background.
_DARK_THRESHOLD = 50

# Letterhead / supplier shown on the worker-specific-costs CSV template.
SUPPLIER_NAME = "STG Infotech (India) LLP"

_CURRENCY_SYMBOLS = {"INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}


@lru_cache(maxsize=1)
def _logo_on_white() -> Image.Image | None:
    """Return the logo with its dark background turned white.

    The supplied PNG has a solid black background (no alpha), which fpdf2
    renders as a black box. We map near-black pixels to white so the logo
    blends into the white PDF page, while preserving the blue mark and the
    white "STG" lettering. A pixel counts as background only when *all* of its
    channels are dark, so the strong-blue parts of the mark are kept intact.
    """
    if not LOGO_PATH.exists():
        return None
    logo = Image.open(LOGO_PATH).convert("RGB")
    r, g, b = logo.split()
    max_channel = ImageChops.lighter(ImageChops.lighter(r, g), b)
    background_mask = max_channel.point(lambda p: 255 if p < _DARK_THRESHOLD else 0)
    white = Image.new("RGB", logo.size, (255, 255, 255))
    return Image.composite(white, logo, background_mask)


def _money(value: float, currency: str) -> str:
    return f"{currency} {value:,.2f}"


def _symbol(currency: str) -> str:
    return _CURRENCY_SYMBOLS.get(currency.upper(), currency)


def _country(currency: str) -> str:
    return "India" if currency.upper() == "INR" else currency


def _num(value: float) -> str:
    """Match the template: a bare 0 for empty lines, 2 decimals otherwise."""
    return "0" if round(value, 2) == 0 else f"{value:.2f}"


def breakdown_to_csv(b: EmployeeBidBreakdown) -> str:
    """Render the breakdown in the STG 'Worker Specific Costs' hourly template.

    The reference workbook places the label in column B, the hourly (currency)
    value in column C, and a one-off note in column D, with a fixed list of
    allowance lines. Our calculated components map onto that list; anything we do
    not model is emitted as 0 so the file lines up with the sheet.
    """
    rk = {row.key: row for row in b.rows}

    def hourly(key: str) -> float:
        row = rk.get(key)
        return row.hourly if row else 0.0

    placement = (
        "New Placement"
        if b.employment_type == EmploymentType.new_hire
        else "Existing Placement"
    )

    def line(*cells: tuple[int, str]) -> list[str]:
        """Build a row from (1-based column, value) pairs, trimmed to the last one."""
        width = max((col for col, _ in cells), default=0)
        out = [""] * width
        for col, val in cells:
            out[col - 1] = val
        return out

    grid: list[list[str]] = []
    grid.extend([[]] * 4)  # rows 1-4 (blank)
    grid.append(line((3, placement)))                                                  # 5
    grid.append(line((3, _country(b.currency))))                                       # 6
    grid.append(line((2, "Supplier Name:"), (3, SUPPLIER_NAME)))                       # 7
    grid.append(line((2, "Worker Name:"), (3, b.name)))                               # 8
    grid.append(line((2, "Max Annual Hours"), (3, f"{b.annual_hours:g}")))            # 9
    grid.append(line((2, "Worker Specific Costs*"), (3, f"Hourly ({_symbol(b.currency)})")))  # 10
    grid.append(line((2, "Worker Payroll (Basic)"), (3, _num(hourly("basic")))))       # 11
    grid.append(line((2, "House Rent Allowance (HRA)"), (3, _num(hourly("hra")))))    # 12
    grid.append(line((2, "Gratuity"), (3, _num(hourly("gratuity"))), (4, "Onetime")))  # 13
    grid.append(line((2, "Provident Fund (PF) - Employers Cont."), (3, _num(hourly("employer_pf")))))      # 14
    grid.append(line((2, "Bonus"), (3, "0")))                                          # 15
    grid.append(line((2, "Paid Time Off"), (3, _num(hourly("pto"))), (4, "Onetime")))  # 16
    grid.append(line((2, "Health Insurance & Life Insurance"), (3, _num(hourly("medical")))))              # 17
    grid.append(line((2, "Driver Allowance"), (3, "0")))                               # 18
    grid.append(line((2, "Stationary Allowance"), (3, "0")))                           # 19
    grid.append(line((2, "Meal Allowance / Coupons"), (3, "0")))                       # 20
    grid.append(line((2, "Transport Allowance"), (3, _num(hourly("conveyance")))))     # 21
    grid.append(line((2, "Internet Allowance"), (3, "0")))                             # 22
    grid.append(line((2, "Phone Allowance"), (3, "0")))                                # 23
    grid.append(line((2, "Vehicle / Fuel Allowance"), (3, "0")))                       # 24
    grid.append(line((2, "Other Worker Specific Cost 1"), (3, _num(hourly("special_pay")))))               # 25
    grid.append(line((2, "Other Worker Specific Cost 2"), (3, "0")))                   # 26
    grid.append(line((2, "CTC"), (3, _num(hourly("grand_total")))))                    # 27
    grid.append(line((2, "Customer Charge Rate (bid rate)"), (3, _num(b.billing_rate_per_hour))))          # 28
    grid.append(line((2, "Mark-up"), (3, f"{b.markup_pct / 100:.2f}")))                # 29

    # Reference rate constants carried from the source workbook (rows 70-74).
    grid.extend([[]] * 40)  # rows 30-69 (blank)
    grid.append(line((11, "Employee Contribution"), (12, "0.12")))                     # 70
    grid.append(line((11, "Employer Contribution"), (12, "0.0833")))                   # 71
    grid.append(line((12, "0.0367")))                                                  # 72
    grid.append(line((12, "0.005")))                                                   # 73
    grid.append(line((12, "0.005")))                                                   # 74

    buf = io.StringIO()
    csv.writer(buf).writerows(grid)
    # Prepend a UTF-8 BOM so Excel renders the currency symbol correctly.
    return "\ufeff" + buf.getvalue()


def _safe(text: str) -> str:
    """fpdf2 core fonts are latin-1; replace anything outside it."""
    return text.encode("latin-1", "replace").decode("latin-1")


def breakdown_to_pdf(b: EmployeeBidBreakdown) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Letterhead: logo on the left, title block to its right.
    text_x = pdf.l_margin
    logo = _logo_on_white()
    if logo is not None:
        logo_h = 16.0
        pdf.image(logo, x=pdf.l_margin, y=pdf.get_y(), h=logo_h)
        text_x = pdf.l_margin + 18

    top_y = pdf.get_y()
    pdf.set_xy(text_x, top_y)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _safe("Employee Cost & Bid Breakdown"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(text_x)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, _safe(f"{b.name}  -  {b.currency} {b.ctc:,.0f} CTC ({b.employment_type.value})"),
             new_x="LMARGIN", new_y="NEXT")

    # Ensure content starts below the logo regardless of text height.
    pdf.set_y(max(pdf.get_y(), top_y + 18))
    pdf.set_draw_color(11, 31, 58)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    # Meta block
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    meta = (
        f"DOJ: {b.effective_date_of_joining.isoformat()}   "
        f"Tenure: {b.tenure_years} yrs   Gratuity yrs: {b.gratuity_years}   "
        f"PTO: {b.pto_days} days   Annual hours: {b.annual_hours}   Markup: {b.markup_pct}%"
    )
    pdf.multi_cell(0, 5, _safe(meta))
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Table header
    widths = [80, 37, 37, 30]
    headers = ["Component", "Monthly", "Annual", "Per hour"]
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(11, 31, 58)
    pdf.set_text_color(255, 255, 255)
    for w, h in zip(widths, headers):
        align = "L" if h == "Component" else "R"
        pdf.cell(w, 8, _safe(h), border=0, align=align, fill=True)
    pdf.ln(8)
    pdf.set_text_color(0, 0, 0)

    for row in b.rows:
        is_total = row.kind.value == "total"
        is_sub = row.kind.value == "subtotal"
        pdf.set_font("Helvetica", "B" if (is_total or is_sub) else "", 10)
        if is_total:
            pdf.set_fill_color(238, 244, 255)
            fill = True
        elif is_sub:
            pdf.set_fill_color(245, 247, 251)
            fill = True
        else:
            fill = False
        cells = [
            (widths[0], row.label, "L"),
            (widths[1], _money(row.monthly, b.currency), "R"),
            (widths[2], _money(row.annual, b.currency), "R"),
            (widths[3], _money(row.hourly, b.currency), "R"),
        ]
        for w, text, align in cells:
            pdf.cell(w, 7, _safe(text), border="B", align=align, fill=fill)
        pdf.ln(7)

    pdf.ln(5)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe(f"Grand total per hour: {_money(b.grand_total_hourly, b.currency)}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 8, _safe(f"Billing rate per hour (+{b.markup_pct}% markup): "
                         f"{_money(b.billing_rate_per_hour, b.currency)}"),
             new_x="LMARGIN", new_y="NEXT")

    out = pdf.output()
    return bytes(out)
