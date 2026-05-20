"""PDF rendering engine — config-driven ReportLab layout.

The visual layout reproduced here is byte-for-byte equivalent (modulo the
embedded PDF timestamp) to the original hardcoded `pdf_generator.py`.
"""
import io
from dataclasses import dataclass, field
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

FONT = "STSong-Light"
TITLE_STYLE = ParagraphStyle("zh_title", fontName=FONT, fontSize=16, alignment=1, leading=22)
SUBTITLE_STYLE = ParagraphStyle("zh_sub", fontName=FONT, fontSize=11, alignment=1, leading=15)
BODY_STYLE = ParagraphStyle("zh_body", fontName=FONT, fontSize=10, leading=14)
SMALL_STYLE = ParagraphStyle("zh_small", fontName=FONT, fontSize=8, leading=11, textColor=colors.grey)

CLINIC_NAME = "慈恩心理治療所"


def _tw_date(d: date | None) -> str:
    if not d:
        return ""
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def _tw_date_range(start: date | None, end: date | None) -> str:
    if start and end:
        return f"{_tw_date(start)} ~ {_tw_date(end)}"
    if start:
        return f"{_tw_date(start)} ~"
    return ""


@dataclass
class DocumentSpec:
    title: str                              # e.g. clinic name
    subtitle: str                           # e.g. "自費諮商收據"
    meta_rows: list[list[str]]              # metadata table rows (label,val,label,val ...)
    meta_col_widths: list[float]           # cm widths for meta table
    table_header: list[str]
    table_rows: list[list[str]]
    table_total_row: list[str] | None
    table_col_widths: list[float]          # cm widths
    table_font_size: int = 10
    table_row_height: float | None = None  # cm; None = auto (set for signature sheets)
    signature: bool = True
    footer: str = ""
    corner_tag: str = ""                   # top-left corner label e.g. "附件四"
    corner_note: str = ""                  # top-right corner note e.g. "106.04修"


def _build_page_elements(spec: DocumentSpec) -> list:
    """Build the ReportLab flowable elements for one page / one DocumentSpec."""
    from reportlab.platypus import PageBreak  # noqa – imported here to keep top-level imports clean

    elements = []

    # ── Corner tags (附件四 style) ──
    if spec.corner_tag or spec.corner_note:
        tag_rows = [[
            Paragraph(spec.corner_tag, BODY_STYLE),
            "",
            Paragraph(spec.corner_note, SMALL_STYLE),
        ]]
        tag_table = Table(tag_rows, colWidths=[3 * cm, 10 * cm, 3 * cm])
        tag_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(tag_table)
        elements.append(Spacer(1, 4))

    elements.append(Paragraph(spec.title, TITLE_STYLE))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(spec.subtitle, SUBTITLE_STYLE))
    elements.append(Spacer(1, 12))

    meta_table = Table(spec.meta_rows, colWidths=[w * cm for w in spec.meta_col_widths])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    rows = [spec.table_header] + [list(r) for r in spec.table_rows]
    if spec.table_total_row is not None:
        rows.append(spec.table_total_row)

    fs = spec.table_font_size
    pad = 4 if fs >= 10 else 3

    # Fixed row height for signature sheets; header row stays auto
    if spec.table_row_height is not None:
        n_data = len(spec.table_rows)
        n_total = 1 if spec.table_total_row is not None else 0
        row_heights = [None] + [spec.table_row_height * cm] * n_data + ([None] * n_total)
    else:
        row_heights = None

    detail_table = Table(
        rows,
        colWidths=[w * cm for w in spec.table_col_widths],
        rowHeights=row_heights,
    )
    ts_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), fs),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
    ]
    if spec.table_total_row is not None:
        ts_cmds += [
            ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, -1), (-1, -1), fs + 1),
        ]
    detail_table.setStyle(TableStyle(ts_cmds))
    elements.append(detail_table)
    elements.append(Spacer(1, 24))

    if spec.signature:
        sig_rows = [["經辦人：＿＿＿＿＿＿＿", "", "負責人：＿＿＿＿＿＿＿"]]
        sig_table = Table(sig_rows, colWidths=[7 * cm, 3 * cm, 7 * cm])
        sig_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 20),
        ]))
        elements.append(sig_table)

    elements.append(Spacer(1, 16))
    elements.append(Paragraph(spec.footer, SMALL_STYLE))

    return elements


def render(spec: DocumentSpec) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    doc.build(_build_page_elements(spec))
    return buf.getvalue()


def render_multi(specs: list[DocumentSpec]) -> bytes:
    """Render multiple DocumentSpecs into a single multi-page PDF."""
    from reportlab.platypus import PageBreak

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    elements = []
    for i, spec in enumerate(specs):
        if i > 0:
            elements.append(PageBreak())
        elements.extend(_build_page_elements(spec))
    doc.build(elements)
    return buf.getvalue()
