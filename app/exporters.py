"""CSV and PDF renderers for an employee bid breakdown."""
import csv
import io
from functools import lru_cache
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageChops

from .bid_schemas import EmployeeBidBreakdown

LOGO_PATH = Path(__file__).resolve().parent / "static" / "logo.png"

# Pixels whose strongest channel is below this are treated as background.
_DARK_THRESHOLD = 50


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


def _meta_rows(b: EmployeeBidBreakdown) -> list[tuple[str, str]]:
    return [
        ("Employee", b.name),
        ("Currency", b.currency),
        ("Annual CTC", f"{b.ctc:,.2f}"),
        ("Employment type", b.employment_type.value),
        ("Date of joining", b.effective_date_of_joining.isoformat()),
        ("Tenure (years)", str(b.tenure_years)),
        ("Gratuity years (rounded)", str(b.gratuity_years)),
        ("PTO days", str(b.pto_days)),
        ("Annual working hours", str(b.annual_hours)),
        ("Markup %", str(b.markup_pct)),
    ]


def breakdown_to_csv(b: EmployeeBidBreakdown) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)

    for key, value in _meta_rows(b):
        writer.writerow([key, value])
    writer.writerow([])

    writer.writerow(["Component", "Monthly", "Annual", "Per hour"])
    for row in b.rows:
        writer.writerow([row.label, f"{row.monthly:.2f}", f"{row.annual:.2f}", f"{row.hourly:.2f}"])
    writer.writerow([])

    writer.writerow(["Grand total per hour", f"{b.grand_total_hourly:.2f}"])
    writer.writerow([f"Billing rate per hour (+{b.markup_pct}% markup)", f"{b.billing_rate_per_hour:.2f}"])

    return buf.getvalue()


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
