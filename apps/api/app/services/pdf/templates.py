"""Template builders — turn a `data` dict into a `DocumentSpec`.

Add a new template:
  1. Write a `build_xxx_spec(data: dict) -> DocumentSpec` function.
  2. Register it in `TEMPLATES`.
  3. Call `generate_pdf("xxx", data)`.
"""
from datetime import date

from .engine import CLINIC_NAME, DocumentSpec, _tw_date, _tw_date_range


def _fmt_date(v) -> str:
    return _tw_date(v) if isinstance(v, date) else str(v)


def build_self_pay_receipt_spec(data: dict) -> DocumentSpec:
    records = data["records"]
    total_amount = data["total_amount"]

    meta_rows = [
        ["收據編號", data["batch_number"], "個案姓名", data["case_name"]],
        ["諮商期間", _tw_date_range(data["period_start"], data["period_end"]),
         "列印日期", _tw_date(date.today())],
    ]

    table_rows = []
    for i, r in enumerate(records, 1):
        table_rows.append([
            str(i),
            _fmt_date(r["session_date"]),
            r.get("therapist_name", ""),
            r.get("session_type", ""),
            f"${r['amount']:,.0f}",
        ])

    return DocumentSpec(
        title=CLINIC_NAME,
        subtitle="自費諮商收據",
        meta_rows=meta_rows,
        meta_col_widths=[3, 6, 3, 5],
        table_header=["#", "諮商日期", "心理師", "服務項目", "金額"],
        table_rows=table_rows,
        table_total_row=["", "", "", "合計", f"${total_amount:,.0f}"],
        table_col_widths=[1.5, 3.5, 3.5, 5, 3.5],
        table_font_size=10,
        signature=True,
        footer=f"此收據由 {CLINIC_NAME} 系統產出",
    )


def build_institution_claim_form_spec(data: dict) -> DocumentSpec:
    records = data["records"]
    total_amount = data["total_amount"]
    external_ref = data.get("external_ref")

    case_count = len({r.get("case_name") for r in records if r.get("case_name")})
    meta_rows = [
        ["請款單號", data["batch_number"], "機構名稱", data["institution_name"]],
        ["請款期間", _tw_date_range(data["period_start"], data["period_end"]),
         "列印日期", _tw_date(date.today())],
        ["總場次", f"{len(records)} 場", "個案數", f"{case_count} 位"],
    ]
    if external_ref:
        meta_rows.append(["外部編號", external_ref, "", ""])

    table_rows = []
    for i, r in enumerate(records, 1):
        table_rows.append([
            str(i),
            r.get("case_name", ""),
            _fmt_date(r["session_date"]),
            r.get("therapist_name", ""),
            r.get("session_type", ""),
            f"${r['amount']:,.0f}",
        ])

    return DocumentSpec(
        title=CLINIC_NAME,
        subtitle="機構請款單",
        meta_rows=meta_rows,
        meta_col_widths=[3, 6, 3, 5],
        table_header=["#", "個案姓名", "諮商日期", "心理師", "諮商類型", "金額"],
        table_rows=table_rows,
        table_total_row=["", "", "", "", "合計", f"${total_amount:,.0f}"],
        table_col_widths=[1.2, 3, 3, 3, 3, 3],
        table_font_size=9,
        signature=True,
        footer=f"此請款單由 {CLINIC_NAME} 系統產出",
    )


def build_jiafuzongxin_attendance_spec(data: dict) -> DocumentSpec:
    """台灣兒童暨家庭扶助基金會南台南家扶中心 — 心理諮商服務簽到表.

    data keys:
      case_name: str
      therapist_name: str
      records: list[{"session_date": date|str, "time_str": str}]
      max_rows: int = 12
    """
    records = data.get("records", [])
    max_rows = data.get("max_rows", 12)
    case_name = data.get("case_name", "")
    therapist_name = data.get("therapist_name", "")

    meta_rows = [[
        "受服務者姓名：", case_name,
        "心理師：", therapist_name,
    ]]

    table_rows = []
    for i in range(1, max_rows + 1):
        if i <= len(records):
            r = records[i - 1]
            table_rows.append([str(i), _fmt_date(r.get("session_date")), r.get("time_str", ""), "", "", ""])
        else:
            table_rows.append([str(i), "", "", "", "", ""])

    return DocumentSpec(
        title="台灣兒童暨家庭扶助基金會南台南家扶中心",
        subtitle="心理諮商服務簽到表",
        meta_rows=meta_rows,
        meta_col_widths=[3.5, 5, 2.5, 5],
        table_header=["次數", "日期", "時間", "受服務者簽名", "諮商師簽名", "備註"],
        table_rows=table_rows,
        table_total_row=None,
        table_col_widths=[1.5, 2.8, 2.8, 3.8, 3.8, 1.8],
        table_font_size=10,
        table_row_height=1.5,
        signature=False,
        footer="備註：本表請於核銷經費時一併附上。",
    )


def build_jiafangzhongxin_attendance_spec(data: dict) -> DocumentSpec:
    """臺南市政府家庭暴力暨性侵害防治中心 — 心理輔導個案簽到表（附件四）.

    data keys:
      case_name: str
      case_number: str        # 系統案號（可空）
      social_worker: str      # 家防中心社工（可空）
      referral_unit: str      # 委託單位/外轄社工（可空）
      records: list[{"session_date": date|str, "time_str": str}]
      max_rows: int = 15
    """
    records = data.get("records", [])
    max_rows = data.get("max_rows", 15)
    case_name = data.get("case_name", "")
    case_number = data.get("case_number", "")
    social_worker = data.get("social_worker", "")
    referral_unit = data.get("referral_unit", "")

    name_display = f"{case_name}（{case_number}）" if case_number else case_name

    meta_rows = [
        ["個案姓名\n（系統案號）", name_display, "家防中心社工", social_worker],
        ["", "", "委託單位/外轄社工", referral_unit],
    ]

    table_rows = []
    for i in range(1, max_rows + 1):
        if i <= len(records):
            r = records[i - 1]
            table_rows.append([str(i), _fmt_date(r.get("session_date")), r.get("time_str", ""), "", "", ""])
        else:
            table_rows.append([str(i), "", "", "", "", ""])

    return DocumentSpec(
        title="臺南市政府家庭暴力暨性侵害防治中心",
        subtitle="心理輔導個案簽到表",
        meta_rows=meta_rows,
        meta_col_widths=[3.5, 4, 3.5, 5],
        table_header=["次數", "日期", "時間", "受輔導者簽名", "諮商師簽名", "備註"],
        table_rows=table_rows,
        table_total_row=None,
        table_col_widths=[1.5, 2.8, 2.8, 3.8, 3.8, 1.8],
        table_font_size=10,
        table_row_height=1.3,
        signature=False,
        footer="備註：本表請於核銷經費時一併附上。",
        corner_tag="附件四",
        corner_note="106.04修",
    )


TEMPLATES = {
    "self_pay_receipt":           build_self_pay_receipt_spec,
    "institution_claim_form":     build_institution_claim_form_spec,
    "jiafuzongxin_attendance":    build_jiafuzongxin_attendance_spec,
    "jiafangzhongxin_attendance": build_jiafangzhongxin_attendance_spec,
}


def generate_pdf(template_key: str, data: dict) -> bytes:
    from .engine import render

    builder = TEMPLATES.get(template_key)
    if builder is None:
        raise ValueError(f"Unknown PDF template: {template_key!r}")
    return render(builder(data))
