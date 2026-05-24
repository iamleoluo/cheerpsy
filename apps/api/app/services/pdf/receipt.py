"""慈恩心理治療所收據產生器

兩聯式版型（完整還原紙本）：
  • 正本（客戶收據聯）—— 上半頁
  • 副本（存根聯）      —— 下半頁
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

# ── 字型設定（嵌入 TTF/TTC，Chrome 相容）────────────────────────────────────
# CID 字型（STSong-Light 等）不嵌入字型資料，Chrome 無法顯示中文。
# 必須使用 TTFont 載入並嵌入字型。依序嘗試：使用者提供的標楷體 →
# macOS 系統華文黑體 → Linux Noto CJK → 最後才 fallback 到 CID。

_FONT_DIR = Path(__file__).parent / "fonts"

CN_FONT: str | None = None
ASCII_FONT = "Helvetica"

_CN_TTF_CANDIDATES = [
    (str(_FONT_DIR / "BiauKai.ttf"), None),                               # 使用者提供標楷體
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),                       # macOS 華文細黑
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),                      # macOS 華文黑體
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),                    # macOS 冬青黑（含繁體）
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),        # Linux Noto CJK
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0),
]

for _path, _idx in _CN_TTF_CANDIDATES:
    try:
        kwargs: dict = {}
        if _idx is not None:
            kwargs["subfontIndex"] = _idx
        pdfmetrics.registerFont(TTFont("ClinFontCN", _path, **kwargs))
        CN_FONT = "ClinFontCN"
        break
    except Exception:
        continue

if CN_FONT is None:
    # 最後 fallback：CID 字型（Chrome 可能無法顯示，但 PDF 結構正確）
    for _cid in ("STKaiti", "STSong-Light"):
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(_cid))
            CN_FONT = _cid
            break
        except Exception:
            continue

if CN_FONT is None:
    CN_FONT = "Helvetica"  # 完全 fallback

try:
    pdfmetrics.registerFont(
        TTFont("TimesNewRoman", "/System/Library/Fonts/Supplemental/Times New Roman.ttf")
    )
    ASCII_FONT = "TimesNewRoman"
except Exception:
    try:
        pdfmetrics.registerFont(
            TTFont("TimesNewRoman", "/System/Library/Fonts/Times.ttc", subfontIndex=0)
        )
        ASCII_FONT = "TimesNewRoman"
    except Exception:
        pass


CLINIC_NAME = "慈恩心理治療所"


def _is_ascii(ch: str) -> bool:
    return ord(ch) < 128


def _mixed_string_width(text: str, size: float) -> float:
    """計算混合中英文字串的繪製寬度。"""
    return sum(
        pdfmetrics.stringWidth(ch, ASCII_FONT if _is_ascii(ch) else CN_FONT, size)
        for ch in text
    )


def _draw_mixed(c: rl_canvas.Canvas, x: float, y: float, text: str, size: float) -> float:
    """逐字切換字型繪製混合字串，回傳結束 x 座標。"""
    cur_x = x
    for ch in text:
        font = ASCII_FONT if _is_ascii(ch) else CN_FONT
        c.setFont(font, size)
        c.drawString(cur_x, y, ch)
        cur_x += pdfmetrics.stringWidth(ch, font, size)
    return cur_x


def _draw_mixed_right(c: rl_canvas.Canvas, x: float, y: float, text: str, size: float) -> None:
    """靠右對齊繪製混合字串（以 x 為右邊界）。"""
    w = _mixed_string_width(text, size)
    _draw_mixed(c, x - w, y, text, size)


def _draw_mixed_centred(c: rl_canvas.Canvas, x_centre: float, y: float, text: str, size: float) -> None:
    """置中繪製混合字串。"""
    w = _mixed_string_width(text, size)
    _draw_mixed(c, x_centre - w / 2, y, text, size)


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

_SESSION_TYPE_ZH = {"in_person": "現場", "online": "線上", "outdoor": "外出"}


@dataclass
class ReceiptData:
    receipt_number: str        # 收據編號
    issue_date: str            # 開立日期（ROC 格式，例 114/04/29）
    payee: str                 # 姓名/單位（空字串 → 不顯示此列）
    fee_category: str          # 收費項目（內部使用；正本不顯示此欄）
    quantity_label: str        # "數量/諮商次數" / "諮商場次" / "數量"
    quantity: str              # "4" / "3 場" / "2 件"
    total_amount: int          # NTD 整數
    note: str = ""             # 備註（支援換行）
    tax_id: str = ""           # 統一編號（非空則在表格加一列）
    session_type_label: str = ""  # "現場" / "線上" / "外出"（空則不顯示）


# ── Canvas 繪圖工具 ─────────────────────────────────────────────────────────

_FONT_SIZE = 10
_LABEL_W = 4.4 * cm
_ROW_H = 0.72 * cm
_LINE_LEADING = _FONT_SIZE * 1.35
ML = 2.0 * cm  # 左邊界


def _wrap_text(text: str, max_w: float, font_size: int) -> list[str]:
    """逐字計算 stringWidth，超過 max_w 時折行（使用混合字型寬度）。"""
    if not text:
        return [""]
    if _mixed_string_width(text, font_size) <= max_w:
        return [text]
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        if _mixed_string_width(test, font_size) > max_w and current:
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
        lines = _wrap_text(value, value_w - 8, font_size) if allow_wrap else [value]
        h = max(min_row_h, len(lines) * _LINE_LEADING + 6)

        # 格線
        c.setStrokeColorRGB(0.45, 0.45, 0.45)
        c.setLineWidth(0.5)
        c.rect(x, y - h, label_w, h)
        c.rect(x + label_w, y - h, value_w, h)

        c.setFillColorRGB(0, 0, 0)

        # 標籤（靠右對齊，混合字型）
        lw = _mixed_string_width(label, font_size)
        label_y = y - h / 2 - font_size * 0.35
        _draw_mixed(c, x + label_w - lw - 4, label_y, label, font_size)

        # 數值（靠左，多行，混合字型）
        total_text_h = len(lines) * _LINE_LEADING
        line_y = y - (h - total_text_h) / 2 - _LINE_LEADING * 0.72
        for line in lines:
            _draw_mixed(c, x + label_w + 4, line_y, line, font_size)
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
        _draw_mixed_centred(c, W / 2, y, CLINIC_NAME, 16)
        c.setFillColorRGB(0, 0, 0)
        y -= 0.9 * cm

        # 「收 據」標題（無條碼框）
        _draw_mixed(c, ML + TW * 0.18, y, "收  據", 20)
        c.setFillColorRGB(0, 0, 0)
        y -= 1.05 * cm

        # 正本標籤
        _draw_mixed(c, ML, y, "正本（客戶收據聯）", 9)
        c.setFillColorRGB(0, 0, 0)
        y -= 0.32 * cm

        # 正本表格
        main_rows: list[tuple[str, str, bool]] = [
            ("收據編號：", data.receipt_number, False),
            ("開立日期：", data.issue_date, False),
        ]
        if data.payee and data.payee.strip():
            main_rows.append(("姓名/單位：", data.payee, False))
        if data.tax_id and data.tax_id.strip():
            main_rows.append(("統一編號：", data.tax_id, False))
        if data.session_type_label:
            main_rows.append(("諮商類型：", data.session_type_label, False))
        main_rows += [
            (data.quantity_label + "：", data.quantity, False),
            ("總計：", amount_ntd, False),
            ("金額：", amount_zh, False),
            ("備註：", data.note, True),
        ]
        y_after = _draw_receipt_table(c, main_rows, ML, y, label_w, value_w, _ROW_H, _FONT_SIZE)

        # 簽名行
        sig_y = y_after - 1.1 * cm
        c.setFillColorRGB(0, 0, 0)
        _draw_mixed(c, ML, sig_y, "開立行政：＿＿＿＿＿＿＿＿", 10)
        _draw_mixed_right(c, W - MR, sig_y, "診療所章", 10)

    else:
        # ── 存根 標題區 ──
        _draw_mixed(c, ML, y, "慈恩心理治療所收據副本（存根聯）", 10)
        c.setFillColorRGB(0, 0, 0)
        y -= 0.5 * cm

        # 存根表格（壓縮版，收費項目合併數量+總計）
        stub_fee = (
            f"{data.fee_category}  數量：{data.quantity}"
            f"  總計：新台幣 {data.total_amount:,} 元"
        )
        stub_rows: list[tuple[str, str, bool]] = [
            ("收據編號：", data.receipt_number, False),
            ("開立日期：", data.issue_date, False),
        ]
        if data.payee and data.payee.strip():
            stub_rows.append(("姓名/單位：", data.payee, False))
        stub_rows += [
            ("收費項目：", stub_fee, True),
            ("金  額：", amount_zh, False),
        ]
        y_after = _draw_receipt_table(c, stub_rows, ML, y, label_w, value_w, _ROW_H, _FONT_SIZE)

        # 簽名行
        sig_y = y_after - 0.8 * cm
        _draw_mixed(c, ML, sig_y, "開立行政：＿＿＿＿＿＿＿＿", 10)
        c.setFillColorRGB(0, 0, 0)


# ── 主入口 ─────────────────────────────────────────────────────────────────

def render_receipt(data: ReceiptData) -> bytes:
    """產生兩聯式收據 PDF（A4，正本上半 + 存根下半）。"""
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)

    # 正本（從頂部往下）
    _draw_section(c, data, H - 1.5 * cm, is_stub=False)

    # 分隔線（實線 + 文字，無虛線）
    div_y = H / 2
    c.setStrokeColorRGB(0.45, 0.45, 0.45)
    c.setLineWidth(0.6)
    c.setDash()
    c.line(ML, div_y, W - 2 * cm, div_y)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    _draw_mixed_centred(c, W / 2, div_y + 3, "慈恩心療所留存", 8)
    c.setFillColorRGB(0, 0, 0)

    # 存根（分隔線下方）
    _draw_section(c, data, div_y - 0.8 * cm, is_stub=True)

    c.save()
    return buf.getvalue()


# ── 4 種類型 Builder ────────────────────────────────────────────────────────

def build_single_session_receipt(record, case) -> ReceiptData:
    """單次諮商收據。"""
    amount = int(record.amount or 0)
    st_label = _SESSION_TYPE_ZH.get(record.session_type or "", "")
    return ReceiptData(
        receipt_number=record.receipt_no or f"R{record.id}",
        issue_date=_tw_date(date.today()),
        payee=case.name if case else "",
        fee_category="心理諮商",
        quantity_label="數量/諮商次數",
        quantity="1",
        total_amount=amount,
        note=f"諮商日期：{_tw_date(record.session_date)}　單次費用：新台幣 {amount:,} 元",
        session_type_label=st_label,
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
        payee=case.name if case else "",
        fee_category="心理諮商",
        quantity_label="數量/諮商次數",
        quantity=str(len(records)),
        total_amount=total,
        note=session_items,
        session_type_label="",
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
        payee=institution.name if institution else "",
        fee_category="心理諮商服務",
        quantity_label="諮商場次",
        quantity=f"{n} 場",
        total_amount=total,
        note=f"服務期間：{period}　共 {n} 場" if period else f"共 {n} 場",
    )


@dataclass
class MultiItemReceiptData:
    receipt_number: str
    issue_date: str
    payee: str
    fee_category: str
    items: list[dict]   # [{date, name, receipt_no, amount}]
    total_amount: int
    note: str = ""
    tax_id: str = ""


def render_multi_item_receipt(data: MultiItemReceiptData) -> bytes:
    """多筆明細整體收據（A4 兩聯式：正本含明細表 + 存根聯）。"""
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)

    amount_ntd = f"新台幣 {data.total_amount:,} 元"
    amount_zh = amount_to_zh(data.total_amount)
    MR = 2.0 * cm
    TW = W - ML - MR
    label_w = _LABEL_W
    value_w = TW - label_w

    # ── 正本 ──────────────────────────────────────────
    y = H - 1.5 * cm
    _draw_mixed_centred(c, W / 2, y, CLINIC_NAME, 16)
    y -= 0.9 * cm
    _draw_mixed(c, ML + TW * 0.18, y, "收  據", 20)
    y -= 1.05 * cm
    _draw_mixed(c, ML, y, "正本（客戶收據聯）", 9)
    y -= 0.32 * cm

    # 上方資訊行（正本含收據編號）
    header_rows: list[tuple[str, str, bool]] = [
        ("收據編號：", data.receipt_number, False),
        ("開立日期：", data.issue_date, False),
    ]
    if data.payee and data.payee.strip():
        header_rows.append(("姓名/單位：", data.payee, False))
    if data.tax_id and data.tax_id.strip():
        header_rows.append(("統一編號：", data.tax_id, False))
    y = _draw_receipt_table(c, header_rows, ML, y, label_w, value_w, _ROW_H, _FONT_SIZE)

    # 明細表格（正本不顯示各筆收據編號，僅顯示日期、諮商方式、金額）
    y -= 0.3 * cm
    col_widths = [2.5 * cm, 8.4 * cm, 2.8 * cm]
    col_headers = ["日期", "諮商方式", "金額"]
    fs = 9

    # 表頭
    row_h = 0.6 * cm
    c.setFillColorRGB(0.92, 0.92, 0.92)
    c.rect(ML, y - row_h, sum(col_widths), row_h, fill=1)
    c.setFillColorRGB(0, 0, 0)
    for i, (hdr, cw) in enumerate(zip(col_headers, col_widths)):
        cx = ML + sum(col_widths[:i])
        c.setStrokeColorRGB(0.45, 0.45, 0.45)
        c.setLineWidth(0.5)
        c.rect(cx, y - row_h, cw, row_h)
        _draw_mixed_centred(c, cx + cw / 2, y - row_h + 3, hdr, fs)
    y -= row_h

    # 明細列
    item_h = 0.55 * cm
    for item in data.items:
        vals = [
            item.get("date", ""),
            item.get("name", ""),
            f"${int(item.get('amount', 0)):,}",
        ]
        for i, (val, cw) in enumerate(zip(vals, col_widths)):
            cx = ML + sum(col_widths[:i])
            c.setStrokeColorRGB(0.45, 0.45, 0.45)
            c.setLineWidth(0.4)
            c.rect(cx, y - item_h, cw, item_h)
            if i == 2:
                _draw_mixed_right(c, cx + cw - 3, y - item_h + 3, val, fs)
            else:
                _draw_mixed(c, cx + 3, y - item_h + 3, val, fs)
        y -= item_h

    # 合計列
    total_h = 0.65 * cm
    c.setStrokeColorRGB(0.45, 0.45, 0.45)
    c.setLineWidth(0.5)
    c.rect(ML, y - total_h, sum(col_widths), total_h)
    c.setFillColorRGB(0, 0, 0)
    _draw_mixed(c, ML + 3, y - total_h + 4, f"合計：{len(data.items)} 筆", fs)
    _draw_mixed_right(c, ML + sum(col_widths) - 3, y - total_h + 4, amount_ntd, fs)
    y -= total_h

    # 大寫金額 + 備註
    y -= 0.3 * cm
    amount_rows: list[tuple[str, str, bool]] = [
        ("金額：", amount_zh, False),
    ]
    if data.note:
        amount_rows.append(("備註：", data.note, True))
    y = _draw_receipt_table(c, amount_rows, ML, y, label_w, value_w, _ROW_H, _FONT_SIZE)

    # 簽名行（保持在正本區域內，不超過分隔線）
    sig_y = max(y - 1.1 * cm, H / 2 + 0.9 * cm)
    _draw_mixed(c, ML, sig_y, "開立行政：＿＿＿＿＿＿＿＿", 10)
    _draw_mixed_right(c, W - MR, sig_y, "診療所章", 10)

    # ── 分隔線 ──────────────────────────────────────
    div_y = H / 2
    c.setStrokeColorRGB(0.45, 0.45, 0.45)
    c.setLineWidth(0.6)
    c.setDash()
    c.line(ML, div_y, W - MR, div_y)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    _draw_mixed_centred(c, W / 2, div_y + 3, "慈恩心療所留存", 8)
    c.setFillColorRGB(0, 0, 0)

    # ── 存根 ──────────────────────────────────────────
    y = div_y - 0.8 * cm
    _draw_mixed(c, ML, y, "慈恩心理治療所收據副本（存根聯）", 10)
    y -= 0.5 * cm

    stub_fee = f"{data.fee_category}  共 {len(data.items)} 筆  總計：{amount_ntd}"
    # 各筆收據編號（存根聯保留，供對帳用）
    item_receipt_nos = "、".join(
        item.get("receipt_no", "") for item in data.items if item.get("receipt_no")
    )
    stub_rows: list[tuple[str, str, bool]] = [
        ("收據編號：", data.receipt_number, False),
        ("開立日期：", data.issue_date, False),
    ]
    if data.payee and data.payee.strip():
        stub_rows.append(("姓名/單位：", data.payee, False))
    stub_rows += [
        ("收費項目：", stub_fee, True),
        ("金  額：", amount_zh, False),
    ]
    if item_receipt_nos:
        stub_rows.append(("各筆編號：", item_receipt_nos, True))
    _draw_receipt_table(c, stub_rows, ML, y, label_w, value_w, _ROW_H, _FONT_SIZE)

    c.save()
    return buf.getvalue()


def build_self_pay_batch_receipt(batch, case, records) -> MultiItemReceiptData:
    """自費批次整體收據 builder。records = list of SessionRecord ORM objects。"""
    items = [
        {
            "date": _tw_date(r.session_date),
            "name": _SESSION_TYPE_ZH.get(r.session_type or "", "現場"),
            "receipt_no": r.receipt_no or f"R{r.id}",
            "amount": int(r.amount or 0),
        }
        for r in sorted(records, key=lambda x: x.session_date)
    ]
    return MultiItemReceiptData(
        receipt_number=batch.batch_number,
        issue_date=_tw_date(date.today()),
        payee=case.name if case else "",
        fee_category="心理諮商",
        items=items,
        total_amount=int(batch.total_amount or 0),
    )


def build_product_receipt(sale) -> ReceiptData:
    """商品收入收據。payee 留空 → 收據不顯示姓名列。"""
    unit_price = int(sale.amount or 0)
    qty = sale.quantity or 1
    total = unit_price * qty
    return ReceiptData(
        receipt_number=sale.receipt_no or f"P{sale.id}",
        issue_date=_tw_date(date.today()),
        payee="",
        fee_category=sale.product_name or "商品",
        quantity_label="數量",
        quantity=f"{qty} 件",
        total_amount=total,
        note=f"單價：新台幣 {unit_price:,} 元",
    )
