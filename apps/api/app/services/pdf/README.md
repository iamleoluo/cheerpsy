# PDF 產生模組 (PDF Generation Module)

設定驅動 (config-driven) 的 PDF 產生模組，底層使用 ReportLab。
讓未來新增報表 / 收據時，只需寫一個「builder 函式」與註冊一行，
不必再複製貼上整段 ReportLab 排版程式碼。

## 架構 (Architecture)

```
caller (router)
   │  generate_pdf(template_key, data)
   ▼
TEMPLATES registry (templates.py)
   │  builder(data) -> DocumentSpec
   ▼
DocumentSpec (engine.py, dataclass)
   │  render(spec)
   ▼
engine.render() ── ReportLab ──> PDF bytes
```

- `engine.py` — 字型註冊、樣式常數、`DocumentSpec` dataclass、`render()`、日期工具。
- `templates.py` — 每個報表一個 `build_*_spec()` builder，`TEMPLATES` 註冊表，`generate_pdf()` 入口。
- `__init__.py` — 對外 API：相容舊簽名的包裝函式 + `generate_pdf` / `DocumentSpec` / `render` / `TEMPLATES`。
- `../pdf_generator.py` — 只剩 backward-compat shim（re-export），舊 caller 不需改動。

## `DocumentSpec` 欄位參考 (Field Reference)

| 欄位 (field) | 型別 (type) | 說明 |
|---|---|---|
| `title` | `str` | 大標題，置中，16pt。一般為診所名稱 `CLINIC_NAME`。 |
| `subtitle` | `str` | 副標題，置中，11pt。例如 `"自費諮商收據"`。 |
| `meta_rows` | `list[list[str]]` | 上方資訊表的列，格式為 `[label, val, label, val]`。 |
| `meta_col_widths` | `list[float]` | 資訊表欄寬，單位為 **cm 數值**（`render` 內乘上 `cm`）。 |
| `table_header` | `list[str]` | 明細表表頭列。 |
| `table_rows` | `list[list[str]]` | 明細表資料列（不含表頭、不含合計列）。 |
| `table_total_row` | `list[str] \| None` | 合計列；`None` 則不畫合計列與其上方粗線。 |
| `table_col_widths` | `list[float]` | 明細表欄寬，**cm 數值**。 |
| `table_font_size` | `int` (預設 10) | 明細表字級。`>=10` 時 padding=4、合計列 `+1`；否則 padding=3。 |
| `signature` | `bool` (預設 True) | 是否顯示「經辦人 / 負責人」簽名列。 |
| `footer` | `str` | 頁尾灰色小字 (8pt)。 |

> 對齊規則固定：明細表第一欄置中 (`#`)，最後一欄靠右（金額）。
> 這正好對應原本 self-pay（5 欄，idx 4）與 institution（6 欄，idx 5）的行為。

## 如何新增一個新模板 (How to add a new template)

1. 在 `templates.py` 寫一個 builder 函式，輸入 `data: dict`，輸出 `DocumentSpec`。
2. 在 `TEMPLATES` 字典註冊 `"<key>": build_<key>_spec`。
3. caller 端呼叫 `generate_pdf("<key>", data)`。
4. （可選）在 `__init__.py` 加一個具名包裝函式以保留型別友善的簽名。

複製即用範例 (copy-paste example)：

```python
# templates.py
def build_petty_cash_report_spec(data: dict) -> DocumentSpec:
    items = data["items"]                         # list[dict]
    total = sum(i["amount"] for i in items)
    rows = [
        [str(i), _fmt_date(it["date"]), it["category"], it["item"],
         f"${it['amount']:,.0f}"]
        for i, it in enumerate(items, 1)
    ]
    return DocumentSpec(
        title=CLINIC_NAME,
        subtitle="零用金支出報表",
        meta_rows=[["期間", data["period"], "列印日期", _tw_date(date.today())]],
        meta_col_widths=[3, 6, 3, 5],
        table_header=["#", "日期", "類別", "項目", "金額"],
        table_rows=rows,
        table_total_row=["", "", "", "合計", f"${total:,.0f}"],
        table_col_widths=[1.5, 3.5, 3.5, 5, 3.5],
        footer=f"此報表由 {CLINIC_NAME} 系統產出",
    )

TEMPLATES["petty_cash_report"] = build_petty_cash_report_spec
```

呼叫：

```python
from app.services.pdf import generate_pdf
pdf_bytes = generate_pdf("petty_cash_report", {"period": "115/05", "items": [...]})
```

未知 key 會丟出 `ValueError`。

## 中文字型 / 民國年日期 (Chinese font / ROC date)

- 字型使用 ReportLab 內建 CID 字型 `STSong-Light`（`engine.py` 模組載入時 `registerFont`）。
  不需外掛 ttf；支援繁中。所有樣式 `fontName` 皆為此字型。
- `_tw_date(d)` 轉民國年：`西元年 - 1911`，格式 `YYY/MM/DD`（例如 2026-05-01 → `115/05/01`）。
- `_tw_date_range(start, end)` 產生 `起 ~ 迄`；只有 start 時為 `起 ~`。
- builder 內處理日期欄位請用 `_fmt_date(v)`（`date` 走民國轉換，其餘 `str()`）。

## 既有兩個模板的 `data` 範例 (existing templates' data dicts)

`self_pay_receipt`：

```python
{
  "batch_number": "R1",
  "case_name": "個案A",
  "period_start": date(2026, 5, 1),
  "period_end": date(2026, 5, 1),
  "records": [
    {"session_date": date(2026, 5, 1), "therapist_name": "王",
     "session_type": "現場", "amount": 2000},
  ],
  "total_amount": 2000,
}
```

`institution_claim_form`（多 `institution_name`、`external_ref`，records 多 `case_name`）：

```python
{
  "batch_number": "B1",
  "institution_name": "某機構",
  "period_start": date(2026, 5, 1),
  "period_end": date(2026, 5, 1),
  "records": [
    {"case_name": "個案A", "session_date": date(2026, 5, 1),
     "therapist_name": "王", "session_type": "現場", "amount": 2000},
  ],
  "total_amount": 2000,
  "external_ref": "EXT1",   # 可選；有值才顯示「外部編號」列
}
```

## 限制與未來擴充 (Limitations / future work)

- 目前版面僅支援：標題 + 副標題 + 一個資訊表 + 一個明細表 + 簽名列 + 頁尾。
- 純表格排版，**不支援** HTML/CSS、自由段落混排、圖片 / logo。
- 無多頁自訂頁首頁尾（沿用 ReportLab `SimpleDocTemplate` 預設分頁）。
- 若未來要加診所 logo：可於 `DocumentSpec` 新增 `logo_path: str | None = None`
  欄位，並在 `render()` 開頭以 `reportlab.platypus.Image` 插入（建議放在 title
  之前或與 title 並排的 Table 中），不影響既有 builder（預設 `None` 即不變）。
- 同理，要加任意段落可新增 `intro_paragraphs: list[str]` 之類欄位，
  在 meta 表前以 `Paragraph(..., BODY_STYLE)` 渲染。
