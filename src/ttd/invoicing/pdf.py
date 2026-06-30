"""PDF invoice rendering (fpdf2). Pure python — no system dependencies."""

from decimal import Decimal
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from ttd.config.schema import Settings
from ttd.core.money import format_money
from ttd.services.invoicing import InvoiceView

ACCENT = (255, 176, 0)  # the ttd amber
INK = (13, 15, 18)
MUTED = (110, 116, 125)
PAPER_GREY = (246, 247, 248)


# em/en dash, bullet, curly quotes → latin-1-safe equivalents
_LATIN_FALLBACK = str.maketrans(
    {0x2014: "-", 0x2013: "-", 0x2022: "*", 0x201C: '"', 0x201D: '"', 0x2019: "'"}
)


def _latin(text: str) -> str:
    """Core PDF fonts are latin-1; transliterate what we can, drop the rest."""
    text = text.translate(_LATIN_FALLBACK)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _money(value: Decimal, currency: str) -> str:
    # fpdf core fonts are latin-1; € etc. survive, but fall back politely
    text = format_money(value, currency)
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return f"{value:,.2f} {currency}"


def render_pdf(view: InvoiceView, settings: Settings, path: Path) -> Path:
    invoice, client, lines = view.invoice, view.client, view.lines
    currency = invoice.currency

    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()
    pdf.set_margins(18, 16, 18)

    # accent letterhead band
    pdf.set_fill_color(*INK)
    pdf.rect(0, 0, pdf.w, 26, style="F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 26, pdf.w, 1.4, style="F")
    pdf.set_y(9)
    pdf.set_text_color(*ACCENT)
    pdf.set_font("helvetica", style="B", size=20)
    pdf.cell(0, 8, "INVOICE", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", size=10)
    pdf.cell(0, 5, f"{invoice.number}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # from / bill-to columns
    pdf.set_y(34)
    top = pdf.get_y()
    pdf.set_text_color(*MUTED)
    pdf.set_font("helvetica", style="B", size=8)
    pdf.cell(90, 4, "FROM", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*INK)
    pdf.set_font("helvetica", size=10)
    sender = [
        settings.user.name or "Your Name",
        settings.user.email,
        *(settings.user.address.splitlines() if settings.user.address else []),
    ]
    for line in filter(None, sender):
        pdf.cell(90, 5, _latin(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(110, top)
    pdf.set_text_color(*MUTED)
    pdf.set_font("helvetica", style="B", size=8)
    pdf.cell(80, 4, "BILL TO", new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_text_color(*INK)
    pdf.set_font("helvetica", size=10)
    billto = [
        client.name,
        client.contact_name,
        client.email,
        *(client.address.splitlines() if client.address else []),
    ]
    for line in filter(None, billto):
        pdf.cell(80, 5, _latin(line), new_x=XPos.LEFT, new_y=YPos.NEXT)

    # meta row
    pdf.set_y(max(pdf.get_y(), top + 30) + 4)
    pdf.set_fill_color(*PAPER_GREY)
    meta = [
        ("ISSUED", invoice.issued_date.strftime("%b %-d, %Y")),
        ("DUE", invoice.due_date.strftime("%b %-d, %Y") if invoice.due_date else "On receipt"),
        ("PERIOD", f"{invoice.period_start:%b %-d} - {invoice.period_end:%b %-d, %Y}"),
        ("TOTAL DUE", _money(invoice.total, currency)),
    ]
    cell_w = (pdf.w - 36) / len(meta)
    y = pdf.get_y()
    for i, (label, value) in enumerate(meta):
        pdf.set_xy(18 + i * cell_w, y)
        pdf.set_text_color(*MUTED)
        pdf.set_font("helvetica", style="B", size=7)
        pdf.cell(cell_w, 8, label, fill=True, new_x=XPos.LEFT, new_y=YPos.NEXT)
        pdf.set_text_color(*INK)
        pdf.set_font("helvetica", style="B" if label == "TOTAL DUE" else "", size=10)
        pdf.cell(cell_w, 7, value, fill=True)
    pdf.set_y(y + 19)

    # lines table
    pdf.set_font("helvetica", size=9)
    with pdf.table(
        col_widths=(20, 95, 18, 22, 25),
        text_align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        borders_layout="HORIZONTAL_LINES",
        line_height=6.5,
        padding=1.2,
    ) as table:
        header = table.row()
        pdf.set_font("helvetica", style="B", size=8)
        for col in ("DATE", "DESCRIPTION", "HOURS", "RATE", "AMOUNT"):
            header.cell(col)
        pdf.set_font("helvetica", size=9)
        for line in lines:
            row = table.row()
            row.cell(line.work_date.strftime("%b %-d"))
            row.cell(_latin(line.description))
            row.cell(f"{line.billed_seconds / 3600:.2f}")
            row.cell(_money(line.rate, currency))
            row.cell(_money(line.amount, currency))

    if view.expense_lines:
        pdf.ln(3)
        pdf.set_font("helvetica", style="B", size=9)
        pdf.cell(0, 6, "REIMBURSABLE EXPENSES", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("helvetica", size=9)
        with pdf.table(
            col_widths=(20, 138, 22),
            text_align=("LEFT", "LEFT", "RIGHT"),
            borders_layout="HORIZONTAL_LINES",
            line_height=6.5,
            padding=1.2,
        ) as etable:
            header = etable.row()
            pdf.set_font("helvetica", style="B", size=8)
            for col in ("DATE", "DESCRIPTION", "AMOUNT"):
                header.cell(col)
            pdf.set_font("helvetica", size=9)
            for eline in view.expense_lines:
                row = etable.row()
                row.cell(eline.incurred_date.strftime("%b %-d"))
                row.cell(_latin(eline.description))
                row.cell(_money(eline.amount, currency))

    # totals box
    pdf.ln(4)
    label_x = pdf.w - 18 - 70
    rows = [("Subtotal", _money(invoice.subtotal, currency))]
    if invoice.tax:
        rows.append((f"Tax ({invoice.tax_rate * 100:.2f}%)", _money(invoice.tax, currency)))
    if invoice.expenses_subtotal:
        rows.append(("Expenses", _money(invoice.expenses_subtotal, currency)))
    rows.append(("Total due", _money(invoice.total, currency)))
    for i, (label, value) in enumerate(rows):
        is_total = i == len(rows) - 1
        pdf.set_x(label_x)
        pdf.set_font("helvetica", style="B" if is_total else "", size=11 if is_total else 9)
        pdf.set_text_color(*(INK if is_total else MUTED))
        pdf.cell(40, 7, label)
        pdf.cell(30, 7, value, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # footer note
    pdf.set_y(-30)
    pdf.set_text_color(*MUTED)
    pdf.set_font("helvetica", style="I", size=8)
    note = invoice.notes or (
        f"Payment due within {settings.invoice.payment_terms_days} days. Thank you!"
    )
    pdf.multi_cell(0, 4, _latin(note))

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path
