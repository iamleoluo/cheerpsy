import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
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


def generate_self_pay_receipt(
    batch_number: str,
    case_name: str,
    period_start: date | None,
    period_end: date | None,
    records: list[dict],
    total_amount: float,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    elements = []

    elements.append(Paragraph(CLINIC_NAME, TITLE_STYLE))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("自費諮商收據", SUBTITLE_STYLE))
    elements.append(Spacer(1, 12))

    meta = [
        ["收據編號", batch_number, "個案姓名", case_name],
        ["諮商期間", _tw_date_range(period_start, period_end), "列印日期", _tw_date(date.today())],
    ]
    meta_table = Table(meta, colWidths=[3 * cm, 6 * cm, 3 * cm, 5 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    header = ["#", "諮商日期", "心理師", "服務項目", "金額"]
    rows = [header]
    for i, r in enumerate(records, 1):
        rows.append([
            str(i),
            _tw_date(r["session_date"]) if isinstance(r["session_date"], date) else str(r["session_date"]),
            r.get("therapist_name", ""),
            r.get("session_type", ""),
            f"${r['amount']:,.0f}",
        ])
    rows.append(["", "", "", "合計", f"${total_amount:,.0f}"])

    detail_table = Table(rows, colWidths=[1.5 * cm, 3.5 * cm, 3.5 * cm, 5 * cm, 3.5 * cm])
    detail_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(detail_table)
    elements.append(Spacer(1, 24))

    sig_rows = [
        ["經辦人：＿＿＿＿＿＿＿", "", "負責人：＿＿＿＿＿＿＿"],
    ]
    sig_table = Table(sig_rows, colWidths=[7 * cm, 3 * cm, 7 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 20),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 16))
    elements.append(Paragraph(f"此收據由 {CLINIC_NAME} 系統產出", SMALL_STYLE))

    doc.build(elements)
    return buf.getvalue()


def generate_institution_claim_form(
    batch_number: str,
    institution_name: str,
    period_start: date | None,
    period_end: date | None,
    records: list[dict],
    total_amount: float,
    external_ref: str | None = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    elements = []

    elements.append(Paragraph(CLINIC_NAME, TITLE_STYLE))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("機構請款單", SUBTITLE_STYLE))
    elements.append(Spacer(1, 12))

    case_count = len({r.get("case_name") for r in records if r.get("case_name")})
    meta = [
        ["請款單號", batch_number, "機構名稱", institution_name],
        ["請款期間", _tw_date_range(period_start, period_end), "列印日期", _tw_date(date.today())],
        ["總場次", f"{len(records)} 場", "個案數", f"{case_count} 位"],
    ]
    if external_ref:
        meta.append(["外部編號", external_ref, "", ""])

    meta_table = Table(meta, colWidths=[3 * cm, 6 * cm, 3 * cm, 5 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    header = ["#", "個案姓名", "諮商日期", "心理師", "諮商類型", "金額"]
    rows = [header]
    for i, r in enumerate(records, 1):
        rows.append([
            str(i),
            r.get("case_name", ""),
            _tw_date(r["session_date"]) if isinstance(r["session_date"], date) else str(r["session_date"]),
            r.get("therapist_name", ""),
            r.get("session_type", ""),
            f"${r['amount']:,.0f}",
        ])
    rows.append(["", "", "", "", "合計", f"${total_amount:,.0f}"])

    detail_table = Table(rows, colWidths=[1.2 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm])
    detail_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (5, 0), (5, -1), "RIGHT"),
        ("FONTSIZE", (0, -1), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(detail_table)
    elements.append(Spacer(1, 24))

    sig_rows = [
        ["經辦人：＿＿＿＿＿＿＿", "", "負責人：＿＿＿＿＿＿＿"],
    ]
    sig_table = Table(sig_rows, colWidths=[7 * cm, 3 * cm, 7 * cm])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 20),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 16))
    elements.append(Paragraph(f"此請款單由 {CLINIC_NAME} 系統產出", SMALL_STYLE))

    doc.build(elements)
    return buf.getvalue()
