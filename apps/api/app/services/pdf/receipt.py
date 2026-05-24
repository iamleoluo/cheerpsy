"""慈恩心理治療所收據產生器

兩聯式版型（完整還原紙本）：
  • 正本（客戶收據聯）—— 上半頁
  • 副本（存根聯）      —— 下半頁
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas as rl_canvas

try:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
except Exception:
    pass

FONT = "STSong-Light"
CLINIC_NAME = "慈恩心理治療所"

# ── 中文金額轉換 ────────────────────────────────────────────────────────────

_DIGITS = "零壹貳參肆伍陸柒捌玖"


def _group4(n: int) -> str:
    """將 0–9999 轉成中文（例：1050 → 壹仟零伍拾）。"""
    if n == 0:
        return ""
    units = [("仟", 1000), ("佰", 100), ("拾", 10), ("", 1)]
    result = ""
    prev_zero = False
    for u, d in units:
        digit = (n // d) % 10
        if digit:
            if prev_zero and result:
                result += "零"
            result += _DIGITS[digit] + u
            prev_zero = False
        else:
            if result:
                prev_zero = True
    return result


def amount_to_zh(amount: int) -> str:
    """將整數 NTD 轉成中文大寫（例：15000 → 新台幣壹萬伍仟元整）。"""
    if amount == 0:
        return "新台幣零元整"
    s = ""
    if amount >= 10000:
        wan = amount // 10000
        rest = amount % 10000
        s += _group4(wan) + "萬"
        if rest:
            if rest < 1000:
                s += "零"
            s += _group4(rest)
    else:
        s = _group4(amount)
    return f"新台幣{s}元整"


def _tw_date(d: date | None) -> str:
    if not d:
        return ""
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


# ── 資料模型 ────────────────────────────────────────────────────────────────

@dataclass
class ReceiptData:
    receipt_number: str   # 收據編號
    issue_date: str       # 開立日期（ROC 格式，例 114/04/29）
    payee: str            # 姓名/單位
    fee_category: str     # 收費項目
    quantity_label: str   # "數量/諮商次數" / "諮商場次" / "數量"
    quantity: str         # "4" / "3 場" / "2 件"
    total_amount: int     # NTD 整數
    note: str = ""        # 備註（支援換行）
    tax_id: str = ""      # 統一編號（非空則在表格加一列）


# ── Canvas 繪圖工具 ─────────────────────────────────────────────────────────

_FONT_SIZE = 10
_LABEL_W = 4.4 * cm
_ROW_H = 0.72 * cm
_LINE_LEADING = _FONT_SIZE * 1.35
ML = 2.0 * cm  # 左邊界


def _wrap_text(c: rl_canvas.Canvas, text: str, max_w: float, font_size: int) -> list[str]:
    """逐字計算 stringWidth，超過 max_w 時折行。"""
    if not text:
        return [""]
    if c.stringWidth(text, FONT, font_size) <= max_w:
        return [text]
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        if c.stringWidth(test, FONT, font_size) > max_w and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _draw_receipt_table(
    c: rl_canvas.Canvas,
    rows: list[tuple[str, str, bool]],
    x: float,
    y_top: float,
    label_w: float,
    value_w: float,
    min_row_h: float,
    font_size: int,
) -> float:
    """繪製兩欄收據表格。rows = [(label, value, wrap_allowed)]
    allow_wrap=True 時 value 欄自動換行，列高動態延伸。
    回傳表格底部 y 座標。"""
    y = y_top
    for label, value, allow_wrap in rows:
        lines = _wrap_text(c, value, value_w - 8, font_size) if allow_wrap else [value]
        h = max(min_row_h, len(lines) * _LINE_LEADING + 6)

        # 格線
        c.setStrokeColorRGB(0.45, 0.45, 0.45)
        c.setLineWidth(0.5)
        c.rect(x, y - h, label_w, h)
        c.rect(x + label_w, y - h, value_w, h)

        c.setFillColorRGB(0, 0, 0)
        c.setFont(FONT, font_size)

        # 標籤（靠右對齊）
        lw = c.stringWidth(label, FONT, font_size)
        label_y = y - h / 2 - font_size * 0.35
        c.drawString(x + label_w - lw - 4, label_y, label)

        # 數值（靠左，多行）
        total_text_h = len(lines) * _LINE_LEADING
        line_y = y - (h - total_text_h) / 2 - _LINE_LEADING * 0.72
        for line in lines:
            c.drawString(x + label_w + 4, line_y, line)
            line_y -= _LINE_LEADING

        y -= h
    return y


# ── 單區段繪製（正本 or 存根）──────────────────────────────────────────────

def _draw_section(
    c: rl_canvas.Canvas,
    data: ReceiptData,
    y_start: float,
    is_stub: bool,
) -> None:
    W, _ = A4
    MR = 2.0 * cm
    TW = W - ML - MR
    label_w = _LABEL_W
    value_w = TW - label_w

    amount_ntd = f"新台幣 {data.total_amount:,} 元"
    amount_zh = amount_to_zh(data.total_amount)

    y = y_start

    if not is_stub:
        # ── 正本 標題區 ──
        c.setFont(FONT, 16)
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(W / 2, y, CLINIC_NAME)
        y -= 0.9 * cm

        # 「收 據」左置 + 條碼框右置
        c.setFont(FONT, 20)
        c.drawString(ML + TW * 0.18, y, "收  據")

        bc_w, bc_h = 5.0 * cm, 1.15 * cm
        bc_x = W - MR - bc_w
        c.setStrokeColorRGB(0.35, 0.35, 0.35)
        c.setLineWidth(0.5)
        c.rect(bc_x, y - 0.15 * cm, bc_w, bc_h)
        c.setFont(FONT, 8)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawCentredString(bc_x + bc_w / 2, y + bc_h / 2 - 4, "（收據編號條碼）")
        c.setFillColorRGB(0, 0, 0)
        y -= 1.05 * cm

        # 正本標籤
        c.setFont(FONT, 9)
        c.drawString(ML, y, "正本（客戶收據聯）")
        y -= 0.32 * cm

        # 正本表格
        main_rows: list[tuple[str, str, bool]] = [
            ("收據編號：", data.receipt_number, False),
            ("開立日期：", data.issue_date, False),
            ("姓名/單位：", data.payee, False),
        ]
        if data.tax_id:
            main_rows.append(("統一編號：", data.tax_id, False))
        main_rows += [
            ("收費項目：", data.fee_category, False),
            (data.quantity_label + "：", data.quantity, False),
            ("總計：", amount_ntd, False),
            ("金額：", amount_zh, False),
            ("備註：", data.note, True),
        ]
        y_after = _draw_receipt_table(c, main_rows, ML, y, label_w, value_w, _ROW_H, _FONT_SIZE)

        # 簽名行
        sig_y = y_after - 1.1 * cm
        c.setFont(FONT, 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(ML, sig_y, "開立行政：＿＿＿＿＿＿＿＿")
        c.drawRightString(W - MR, sig_y, "診療所章")

    else:
        # ── 存根 標題區 ──
        c.setFont(FONT, 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(ML, y, "慈恩心理治療所收據副本（存根聯）")
        y -= 0.5 * cm

        # 存根表格（壓縮版，收費項目合併數量+總計）
        stub_fee = (
            f"{data.fee_category}  數量：{data.quantity}"
            f"  總計：新台幣 {data.total_amount:,} 元"
        )
        stub_rows: list[tuple[str, str, bool]] = [
            ("收據編號：", data.receipt_number, False),
            ("開立日期：", data.issue_date, False),
            ("姓名/單位：", data.payee, False),
            ("收費項目：", stub_fee, True),
            ("金  額：", amount_zh, False),
        ]
        y_after = _draw_receipt_table(c, stub_rows, ML, y, label_w, value_w, _ROW_H, _FONT_SIZE)

        # 簽名行
        sig_y = y_after - 0.8 * cm
        c.setFont(FONT, 10)
        c.drawString(ML, sig_y, "開立行政：＿＿＿＿＿＿＿＿")


# ── 主入口 ─────────────────────────────────────────────────────────────────

def render_receipt(data: ReceiptData) -> bytes:
    """產生兩聯式收據 PDF（A4，正本上半 + 存根下半）。"""
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)

    # 正本（從頂部往下）
    _draw_section(c, data, H - 1.5 * cm, is_stub=False)

    # 分隔虛線
    div_y = H / 2
    c.setDash(3, 3)
    c.setLineWidth(0.5)
    c.setStrokeColorRGB(0.5, 0.5, 0.5)
    c.line(ML, div_y, W - 2 * cm, div_y)
    c.setDash()

    c.setFont(FONT, 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    label = "─────────────────── 慈恩心療所留存 ───────────────────"
    c.drawCentredString(W / 2, div_y + 3, label)
    c.setFillColorRGB(0, 0, 0)

    # 存根（分隔線下方）
    _draw_section(c, data, div_y - 0.8 * cm, is_stub=True)

    c.save()
    return buf.getvalue()


# ── 4 種類型 Builder ────────────────────────────────────────────────────────

def build_single_session_receipt(record, case) -> ReceiptData:
    """單次諮商收據。"""
    amount = int(record.amount or 0)
    return ReceiptData(
        receipt_number=record.receipt_no or f"R{record.id}",
        issue_date=_tw_date(date.today()),
        payee=case.name if case else "——",
        fee_category="心理諮商",
        quantity_label="數量/諮商次數",
        quantity="1",
        total_amount=amount,
        note=f"諮商日期：{_tw_date(record.session_date)}　單次費用：新台幣 {amount:,} 元",
    )


def build_multi_session_receipt(batch, case, records: list[dict]) -> ReceiptData:
    """多次諮商收據（自費核銷案）。"""
    total = int(batch.total_amount or 0)
    session_items = "　".join(
        f"{_tw_date(r['session_date'])} ${int(r['amount']):,}"
        for r in sorted(records, key=lambda x: x["session_date"])
    )
    return ReceiptData(
        receipt_number=batch.batch_number,
        issue_date=_tw_date(date.today()),
        payee=case.name if case else "——",
        fee_category="心理諮商",
        quantity_label="數量/諮商次數",
        quantity=str(len(records)),
        total_amount=total,
        note=session_items,
    )


def build_institution_receipt(batch, institution, records: list[dict]) -> ReceiptData:
    """機構開立收據（機構核銷案）。"""
    total = int(batch.total_amount or 0)
    period = ""
    if batch.period_start and batch.period_end:
        period = f"{_tw_date(batch.period_start)} ~ {_tw_date(batch.period_end)}"
    elif batch.period_start:
        period = f"{_tw_date(batch.period_start)} ~"
    n = len(records)
    return ReceiptData(
        receipt_number=batch.batch_number,
        issue_date=_tw_date(date.today()),
        payee=institution.name if institution else "——",
        fee_category="心理諮商服務",
        quantity_label="諮商場次",
        quantity=f"{n} 場",
        total_amount=total,
        note=f"服務期間：{period}　共 {n} 場" if period else f"共 {n} 場",
    )


def build_product_receipt(sale) -> ReceiptData:
    """商品收入收據。"""
    unit_price = int(sale.amount or 0)
    qty = sale.quantity or 1
    total = unit_price * qty
    return ReceiptData(
        receipt_number=sale.receipt_no or f"P{sale.id}",
        issue_date=_tw_date(date.today()),
        payee="——",
        fee_category=sale.product_name or "商品",
        quantity_label="數量",
        quantity=f"{qty} 件",
        total_amount=total,
        note=f"單價：新台幣 {unit_price:,} 元",
    )
