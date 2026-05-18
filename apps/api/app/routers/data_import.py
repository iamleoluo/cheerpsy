"""
Data import router — supports dry-run preview, supplement (insert-only), and clean (upsert) modes.
All endpoints require admin role.
Clean mode additionally requires the admin's current password to prevent accidental overwrites.
"""

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.auth.password import verify_password
from app.database import get_db
from app.models.case import Case
from app.models.institution import Institution
from app.models.petty_cash import PettyCash
from app.models.product_sales import ProductSale
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/data-import", tags=["data-import"])

SUPPORTED_TABLES = {
    "session_records", "cases", "users", "institutions", "petty_cash", "product_sales"
}


class ImportResult(BaseModel):
    table: str
    mode: str
    total_rows: int
    would_insert: int
    would_update: int
    would_skip: int
    errors: list[dict]
    warnings: list[dict]
    committed: bool = False


def _parse_csv(content: bytes) -> list[dict]:
    """Parse CSV bytes (with or without UTF-8 BOM) into list of dicts."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _str(val) -> str:
    return (val or "").strip()


def _int_or_none(val) -> Optional[int]:
    v = _str(val)
    if not v:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _float_or_none(val) -> Optional[float]:
    v = _str(val)
    if not v:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _bool_val(val) -> Optional[bool]:
    v = _str(val).lower()
    if v in ("true", "是", "1", "yes"):
        return True
    if v in ("false", "否", "0", "no"):
        return False
    return None


def _model_to_dict(obj) -> dict:
    """Serialize a SQLAlchemy model instance to a plain dict (for audit before/after)."""
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name, None)
        result[col.name] = val
    return result


# ── Per-table validators ──────────────────────────────────────────────────────

def _validate_session_records(rows: list[dict], db: Session) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    therapist_ids = {u.id for u in db.query(User).filter(User.role == "therapist").all()}
    case_ids = {c.id for c in db.query(Case).all()}
    batch_ids_set = set()
    try:
        from app.models.claim_batch import ClaimBatch
        batch_ids_set = {b.id for b in db.query(ClaimBatch).all()}
    except Exception:
        pass

    existing_by_id = {r.id: r for r in db.query(SessionRecord).all()}

    for i, row in enumerate(rows, start=2):  # row 1 = header
        rnum = i

        # Required fields
        if not _str(row.get("session_date", "")) and not _str(row.get("日期", "")):
            errors.append({"row": rnum, "field": "session_date/日期", "value": "", "message": "session_date 為必填"})
        tid = _int_or_none(row.get("therapist_id") or row.get("心理師ID"))
        if tid is None:
            errors.append({"row": rnum, "field": "therapist_id/心理師ID", "value": "", "message": "therapist_id 為必填"})
        elif tid not in therapist_ids:
            errors.append({"row": rnum, "field": "therapist_id/心理師ID", "value": str(tid), "message": f"therapist_id {tid} 不存在或非心理師"})
        amt = _float_or_none(row.get("amount") or row.get("金額"))
        if amt is None:
            errors.append({"row": rnum, "field": "amount/金額", "value": "", "message": "amount 為必填"})
        elif amt < 0:
            errors.append({"row": rnum, "field": "amount/金額", "value": str(amt), "message": "amount 不可為負數"})

        # FK checks
        cid = _int_or_none(row.get("case_id") or row.get("個案ID"))
        if cid is not None and cid not in case_ids:
            errors.append({"row": rnum, "field": "case_id/個案ID", "value": str(cid), "message": f"case_id {cid} 不存在"})
        bid = _int_or_none(row.get("claim_batch_id") or row.get("核銷案ID"))
        if bid is not None and bid not in batch_ids_set:
            errors.append({"row": rnum, "field": "claim_batch_id/核銷案ID", "value": str(bid), "message": f"claim_batch_id {bid} 不存在"})

        # Enum checks
        ps = _str(row.get("payment_status") or row.get("收款狀態"))
        if ps and ps not in ("unpaid", "pending_claim", "paid"):
            errors.append({"row": rnum, "field": "payment_status/收款狀態", "value": ps, "message": "payment_status 須為 unpaid/pending_claim/paid"})
        fs = _str(row.get("funding_source") or row.get("經費來源"))
        if fs and fs not in ("self_pay", "institution"):
            errors.append({"row": rnum, "field": "funding_source/經費來源", "value": fs, "message": "funding_source 須為 self_pay/institution 或空"})
        pm = _str(row.get("payment_method") or row.get("付款方式"))
        if pm and pm not in ("cash", "transfer"):
            errors.append({"row": rnum, "field": "payment_method/付款方式", "value": pm, "message": "payment_method 須為 cash/transfer 或空"})

        # Range
        cr = _float_or_none(row.get("commission_rate_used") or row.get("抽成比例"))
        if cr is not None and not (0 <= cr <= 1):
            errors.append({"row": rnum, "field": "commission_rate_used/抽成比例", "value": str(cr), "message": "抽成比例須介於 0~1"})
        disc = _float_or_none(row.get("discount_amount") or row.get("折扣金額"))
        if disc is not None and amt is not None and disc > amt:
            warnings.append({"row": rnum, "field": "discount_amount/折扣金額", "message": f"折扣金額({disc})大於金額({amt})"})

        # Business rule warnings
        rec_id = _int_or_none(row.get("id") or row.get("ID"))
        existing = existing_by_id.get(rec_id) if rec_id else None
        if existing and bid is not None and existing.claim_batch_id:
            warnings.append({"row": rnum, "field": "claim_batch_id/核銷案ID", "message": "此記錄已綁定核銷案，更改 payment_status 可能影響核銷流程"})
        is_void = _bool_val(row.get("is_void") or row.get("是否作廢"))
        if existing and existing.is_void and is_void is False:
            warnings.append({"row": rnum, "field": "is_void/是否作廢", "message": "正在取消作廢標記，請確認此操作"})
        receipt_no = _str(row.get("receipt_no") or row.get("收據編號"))
        if existing and receipt_no and existing.receipt_no and receipt_no != existing.receipt_no:
            warnings.append({"row": rnum, "field": "receipt_no/收據編號", "message": f"收據編號將從 {existing.receipt_no} 變更為 {receipt_no}，可能影響歷史查詢"})
        if ps == "paid" and not _str(row.get("paid_at") or row.get("付款時間")):
            warnings.append({"row": rnum, "field": "paid_at/付款時間", "message": "payment_status=paid 但付款時間為空"})
        if is_void and not _str(row.get("void_reason") or row.get("作廢原因")):
            warnings.append({"row": rnum, "field": "void_reason/作廢原因", "message": "is_void=True 但作廢原因為空"})

    return errors, warnings


def _validate_cases(rows: list[dict], db: Session) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    therapist_ids = {u.id for u in db.query(User).all()}
    inst_ids = {i.id for i in db.query(Institution).all()}

    for i, row in enumerate(rows, start=2):
        rnum = i
        if not _str(row.get("name") or row.get("姓名")):
            errors.append({"row": rnum, "field": "name/姓名", "value": "", "message": "個案姓名為必填"})
        tid = _int_or_none(row.get("therapist_id") or row.get("心理師ID") or row.get("負責心理師ID"))
        if tid is None:
            errors.append({"row": rnum, "field": "therapist_id", "value": "", "message": "therapist_id 為必填"})
        elif tid not in therapist_ids:
            errors.append({"row": rnum, "field": "therapist_id", "value": str(tid), "message": f"therapist_id {tid} 不存在"})
        fs = _str(row.get("funding_source") or row.get("經費來源"))
        if not fs:
            errors.append({"row": rnum, "field": "funding_source/經費來源", "value": "", "message": "經費來源為必填"})
        elif fs not in ("self_pay", "institution"):
            errors.append({"row": rnum, "field": "funding_source/經費來源", "value": fs, "message": "須為 self_pay 或 institution"})
        inst_id = _int_or_none(row.get("institution_id") or row.get("機構ID"))
        if fs == "institution" and inst_id is None:
            errors.append({"row": rnum, "field": "institution_id/機構ID", "value": "", "message": "經費來源=institution 時 institution_id 為必填"})
        if inst_id is not None and inst_id not in inst_ids:
            errors.append({"row": rnum, "field": "institution_id/機構ID", "value": str(inst_id), "message": f"institution_id {inst_id} 不存在"})
        status = _str(row.get("status") or row.get("狀態"))
        if status and status not in ("initial", "ongoing", "closed", "hold"):
            errors.append({"row": rnum, "field": "status/狀態", "value": status, "message": "status 須為 initial/ongoing/closed/hold"})
        bc = _str(row.get("billing_cycle") or row.get("計費週期"))
        if bc and bc not in ("once", "monthly", "biweekly", "weekly"):
            errors.append({"row": rnum, "field": "billing_cycle/計費週期", "value": bc, "message": "billing_cycle 須為 once/monthly/biweekly/weekly"})
        gender = _str(row.get("gender") or row.get("性別"))
        if gender and gender not in ("male", "female", "other"):
            errors.append({"row": rnum, "field": "gender/性別", "value": gender, "message": "gender 須為 male/female/other 或空"})

    return errors, warnings


def _validate_users(rows: list[dict], db: Session) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    existing_by_id = {u.id: u for u in db.query(User).all()}
    existing_emails = {u.email: u.id for u in db.query(User).all()}
    existing_codes = {u.user_code: u.id for u in db.query(User).all() if u.user_code}
    csv_emails: dict[str, int] = {}
    csv_codes: dict[str, int] = {}

    for i, row in enumerate(rows, start=2):
        rnum = i
        rec_id = _int_or_none(row.get("id") or row.get("ID"))
        email = _str(row.get("email") or row.get("Email"))
        if not email:
            errors.append({"row": rnum, "field": "email/Email", "value": "", "message": "email 為必填"})
        else:
            if email in csv_emails:
                errors.append({"row": rnum, "field": "email/Email", "value": email, "message": f"email 與第 {csv_emails[email]} 列重複"})
            else:
                csv_emails[email] = rnum
            db_uid = existing_emails.get(email)
            if db_uid and db_uid != rec_id:
                errors.append({"row": rnum, "field": "email/Email", "value": email, "message": f"email 已被 id={db_uid} 的使用者使用"})
        if not _str(row.get("name") or row.get("姓名")):
            errors.append({"row": rnum, "field": "name/姓名", "value": "", "message": "姓名為必填"})
        role = _str(row.get("role") or row.get("角色"))
        if not role:
            errors.append({"row": rnum, "field": "role/角色", "value": "", "message": "role 為必填"})
        elif role not in ("admin", "accountant", "staff", "therapist"):
            errors.append({"row": rnum, "field": "role/角色", "value": role, "message": "role 須為 admin/accountant/staff/therapist"})
        code = _str(row.get("user_code") or row.get("代碼"))
        if code:
            if code in csv_codes:
                errors.append({"row": rnum, "field": "user_code/代碼", "value": code, "message": f"user_code 與第 {csv_codes[code]} 列重複"})
            else:
                csv_codes[code] = rnum
            db_uid = existing_codes.get(code)
            if db_uid and db_uid != rec_id:
                errors.append({"row": rnum, "field": "user_code/代碼", "value": code, "message": f"user_code 已被 id={db_uid} 的使用者使用"})
        cr = _float_or_none(row.get("commission_rate") or row.get("抽成比例"))
        if cr is not None and not (0 <= cr <= 1):
            errors.append({"row": rnum, "field": "commission_rate/抽成比例", "value": str(cr), "message": "抽成比例須介於 0~1"})
        bp = _float_or_none(row.get("base_price") or row.get("預設價格"))
        if bp is not None and bp < 0:
            errors.append({"row": rnum, "field": "base_price/預設價格", "value": str(bp), "message": "預設價格不可為負數"})

    return errors, warnings


def _validate_institutions(rows: list[dict], db: Session) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    existing_names = {i.name: i.id for i in db.query(Institution).all()}
    existing_codes = {i.code: i.id for i in db.query(Institution).all() if i.code}

    for i, row in enumerate(rows, start=2):
        rnum = i
        rec_id = _int_or_none(row.get("id") or row.get("ID"))
        name = _str(row.get("name") or row.get("機構名稱"))
        if not name:
            errors.append({"row": rnum, "field": "name/機構名稱", "value": "", "message": "機構名稱為必填"})
        else:
            db_id = existing_names.get(name)
            if db_id and db_id != rec_id:
                errors.append({"row": rnum, "field": "name/機構名稱", "value": name, "message": f"機構名稱已存在 (id={db_id})"})
        code = _str(row.get("code") or row.get("代號"))
        if code:
            db_id = existing_codes.get(code)
            if db_id and db_id != rec_id:
                errors.append({"row": rnum, "field": "code/代號", "value": code, "message": f"機構代號已存在 (id={db_id})"})

    return errors, warnings


def _validate_petty_cash(rows: list[dict], db: Session) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    for i, row in enumerate(rows, start=2):
        rnum = i
        if not _str(row.get("date") or row.get("日期")):
            errors.append({"row": rnum, "field": "date/日期", "value": "", "message": "日期為必填"})
        if _float_or_none(row.get("amount") or row.get("金額")) is None:
            errors.append({"row": rnum, "field": "amount/金額", "value": "", "message": "金額為必填"})
        cat = _str(row.get("category") or row.get("類別"))
        if not cat:
            errors.append({"row": rnum, "field": "category/類別", "value": "", "message": "類別為必填"})
        elif cat not in ("cleaning", "supplies", "electricity", "water", "other"):
            errors.append({"row": rnum, "field": "category/類別", "value": cat, "message": "類別須為 cleaning/supplies/electricity/water/other"})

    return errors, warnings


def _validate_product_sales(rows: list[dict], db: Session) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    for i, row in enumerate(rows, start=2):
        rnum = i
        if not _str(row.get("sale_date") or row.get("日期")):
            errors.append({"row": rnum, "field": "sale_date/日期", "value": "", "message": "銷售日期為必填"})
        if not _str(row.get("product_name") or row.get("商品名稱")):
            errors.append({"row": rnum, "field": "product_name/商品名稱", "value": "", "message": "商品名稱為必填"})
        if _float_or_none(row.get("amount") or row.get("金額")) is None:
            errors.append({"row": rnum, "field": "amount/金額", "value": "", "message": "金額為必填"})
        pm = _str(row.get("payment_method") or row.get("付款方式"))
        if pm and pm not in ("cash", "transfer"):
            errors.append({"row": rnum, "field": "payment_method/付款方式", "value": pm, "message": "付款方式須為 cash/transfer 或空"})

    return errors, warnings


VALIDATORS = {
    "session_records": _validate_session_records,
    "cases": _validate_cases,
    "users": _validate_users,
    "institutions": _validate_institutions,
    "petty_cash": _validate_petty_cash,
    "product_sales": _validate_product_sales,
}


def _apply_session_record(existing: Optional[SessionRecord], row: dict) -> dict:
    """Map CSV row fields to session_records model fields. Returns dict of fields to set."""
    from datetime import datetime, date as date_type
    fields: dict = {}

    def _date(val):
        v = _str(val)
        if not v:
            return None
        try:
            return date_type.fromisoformat(v[:10])
        except Exception:
            return None

    def _dt(val):
        v = _str(val)
        if not v:
            return None
        try:
            return datetime.fromisoformat(v)
        except Exception:
            return None

    def _dec(val):
        f = _float_or_none(val)
        return f  # SQLAlchemy accepts float for Numeric

    fields["session_date"] = _date(row.get("session_date") or row.get("日期"))
    fields["therapist_id"] = _int_or_none(row.get("therapist_id") or row.get("心理師ID"))
    fields["case_id"] = _int_or_none(row.get("case_id") or row.get("個案ID"))
    fields["room_id"] = _int_or_none(row.get("room_id") or row.get("空間ID"))
    fields["session_type"] = _str(row.get("session_type") or row.get("類型")) or "in_person"
    fields["fee_category"] = _str(row.get("fee_category") or row.get("費用類別")) or "counseling"
    fields["amount"] = _dec(row.get("amount") or row.get("金額")) or 0
    fields["discount_amount"] = _dec(row.get("discount_amount") or row.get("折扣金額")) or 0
    fields["discount_note"] = _str(row.get("discount_note") or row.get("折扣備註")) or None
    fields["payment_status"] = _str(row.get("payment_status") or row.get("收款狀態")) or "unpaid"
    fields["payment_method"] = _str(row.get("payment_method") or row.get("付款方式")) or None
    fields["payment_note"] = _str(row.get("payment_note") or row.get("付款備註")) or None
    fields["paid_at"] = _dt(row.get("paid_at") or row.get("付款時間"))
    fields["receipt_no"] = _str(row.get("receipt_no") or row.get("收據編號")) or None
    fields["is_void"] = _bool_val(row.get("is_void") or row.get("是否作廢")) or False
    fields["void_reason"] = _str(row.get("void_reason") or row.get("作廢原因")) or None
    fields["voided_at"] = _dt(row.get("voided_at") or row.get("作廢時間"))
    fields["voided_by"] = _int_or_none(row.get("voided_by") or row.get("作廢者ID"))
    fields["funding_source"] = _str(row.get("funding_source") or row.get("經費來源")) or None
    fields["commission_rate_used"] = _dec(row.get("commission_rate_used") or row.get("抽成比例"))
    fields["claim_batch_id"] = _int_or_none(row.get("claim_batch_id") or row.get("核銷案ID"))
    fields["claim_number"] = _str(row.get("claim_number") or row.get("請款單號")) or None
    fields["receipt_number"] = _str(row.get("receipt_number") or row.get("到款收據")) or None
    fields["appointment_id"] = _int_or_none(row.get("appointment_id") or row.get("預約ID"))
    return {k: v for k, v in fields.items() if v is not None or k in ("is_void", "discount_amount")}


def _apply_case(existing: Optional[Case], row: dict) -> dict:
    from datetime import date as date_type
    fields: dict = {}

    def _date(val):
        v = _str(val)
        if not v:
            return None
        try:
            return date_type.fromisoformat(v[:10])
        except Exception:
            return None

    fields["name"] = _str(row.get("name") or row.get("姓名")) or None
    fields["gender"] = _str(row.get("gender") or row.get("性別")) or None
    fields["birth_date"] = _date(row.get("birth_date") or row.get("出生日期"))
    fields["phone"] = _str(row.get("phone") or row.get("手機")) or None
    fields["phone_home"] = _str(row.get("phone_home") or row.get("市話")) or None
    fields["address"] = _str(row.get("address") or row.get("地址")) or None
    fields["emergency_contact"] = _str(row.get("emergency_contact") or row.get("緊急聯絡人")) or None
    fields["emergency_phone"] = _str(row.get("emergency_phone") or row.get("緊急電話1")) or None
    fields["emergency_phone2"] = _str(row.get("emergency_phone2") or row.get("緊急電話2")) or None
    fields["initial_visit_date"] = _date(row.get("initial_visit_date") or row.get("進案日"))
    fields["funding_source"] = _str(row.get("funding_source") or row.get("經費來源")) or "self_pay"
    fields["institution_id"] = _int_or_none(row.get("institution_id") or row.get("機構ID"))
    fields["therapist_id"] = _int_or_none(row.get("therapist_id") or row.get("心理師ID") or row.get("負責心理師ID"))
    fields["status"] = _str(row.get("status") or row.get("狀態")) or "ongoing"
    fields["billing_cycle"] = _str(row.get("billing_cycle") or row.get("計費週期")) or "once"
    fields["referral_source"] = _str(row.get("referral_source") or row.get("轉介來源")) or None
    fields["session_location"] = _str(row.get("session_location") or row.get("會談地點")) or None
    fields["notes"] = _str(row.get("notes") or row.get("備註")) or None
    fields["case_code"] = _str(row.get("case_code") or row.get("案號")) or None
    fields["case_number"] = _str(row.get("case_number") or row.get("正式案號")) or None
    return fields


def _apply_institution(existing, row: dict) -> dict:
    return {
        "name": _str(row.get("name") or row.get("機構名稱")) or None,
        "code": _str(row.get("code") or row.get("代號")) or None,
        "is_active": _bool_val(row.get("is_active")) if row.get("is_active") else True,
    }


def _apply_petty_cash(existing, row: dict) -> dict:
    from datetime import date as date_type

    def _date(val):
        v = _str(val)
        if not v:
            return None
        try:
            return date_type.fromisoformat(v[:10])
        except Exception:
            return None

    return {
        "date": _date(row.get("date") or row.get("日期")),
        "amount": _float_or_none(row.get("amount") or row.get("金額")),
        "category": _str(row.get("category") or row.get("類別")),
        "description": _str(row.get("description") or row.get("說明")) or None,
        "receipt_note": _str(row.get("receipt_note") or row.get("收據備註")) or None,
        "balance_after": _float_or_none(row.get("balance_after") or row.get("餘額")) or 0,
    }


def _apply_product_sale(existing, row: dict) -> dict:
    from datetime import date as date_type

    def _date(val):
        v = _str(val)
        if not v:
            return None
        try:
            return date_type.fromisoformat(v[:10])
        except Exception:
            return None

    return {
        "sale_date": _date(row.get("sale_date") or row.get("日期")),
        "product_name": _str(row.get("product_name") or row.get("商品名稱")) or None,
        "amount": _float_or_none(row.get("amount") or row.get("金額")),
        "quantity": _int_or_none(row.get("quantity") or row.get("數量")) or 1,
        "payment_method": _str(row.get("payment_method") or row.get("付款方式")) or "cash",
        "payment_note": _str(row.get("payment_note") or row.get("付款備註")) or None,
        "is_void": _bool_val(row.get("is_void")) or False,
        "void_reason": _str(row.get("void_reason") or row.get("作廢原因")) or None,
    }


def _apply_user(existing, row: dict) -> dict:
    # NEVER include password_hash
    fields = {
        "email": _str(row.get("email") or row.get("Email")) or None,
        "name": _str(row.get("name") or row.get("姓名")) or None,
        "role": _str(row.get("role") or row.get("角色")) or None,
        "user_code": _str(row.get("user_code") or row.get("代碼")) or None,
        "commission_rate": _float_or_none(row.get("commission_rate") or row.get("抽成比例")),
        "base_price": _float_or_none(row.get("base_price") or row.get("預設價格")),
        "is_active": _bool_val(row.get("is_active") or row.get("啟用")),
    }
    return {k: v for k, v in fields.items() if v is not None}


TABLE_MODEL_MAP = {
    "session_records": (SessionRecord, _apply_session_record),
    "cases": (Case, _apply_case),
    "users": (User, _apply_user),
    "institutions": (Institution, _apply_institution),
    "petty_cash": (PettyCash, _apply_petty_cash),
    "product_sales": (ProductSale, _apply_product_sale),
}

TABLE_NAME_MAP = {
    "session_records": "session_records",
    "cases": "cases",
    "users": "users",
    "institutions": "institutions",
    "petty_cash": "petty_cash",
    "product_sales": "product_sales",
}


def _run_import(
    table: str,
    rows: list[dict],
    errors: list[dict],
    warnings: list[dict],
    mode: str,  # dry_run | supplement | clean
    current_user: User,
    db: Session,
    admin_password: Optional[str] = None,
) -> ImportResult:
    # Build set of errored rows (1-indexed starting at 2 for data rows)
    errored_rows = {e["row"] for e in errors}

    if mode == "clean" and admin_password is not None:
        if not verify_password(admin_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="管理員密碼不正確")

    Model, apply_fn = TABLE_MODEL_MAP[table]
    db_table_name = TABLE_NAME_MAP[table]

    would_insert = would_update = would_skip = 0

    if mode == "dry_run":
        for i, row in enumerate(rows, start=2):
            if i in errored_rows:
                continue
            rec_id = _int_or_none(row.get("id") or row.get("ID"))
            if rec_id:
                existing = db.get(Model, rec_id)
                if existing:
                    would_update += 1
                else:
                    would_insert += 1
            else:
                would_insert += 1

        return ImportResult(
            table=table, mode=mode,
            total_rows=len(rows),
            would_insert=would_insert, would_update=would_update, would_skip=would_skip,
            errors=errors, warnings=warnings, committed=False,
        )

    # supplement or clean — actually write
    for i, row in enumerate(rows, start=2):
        if i in errored_rows:
            would_skip += 1
            continue

        rec_id = _int_or_none(row.get("id") or row.get("ID"))
        existing = db.get(Model, rec_id) if rec_id else None

        if mode == "supplement":
            if existing:
                would_skip += 1
                continue
            # INSERT new record
            fields = apply_fn(None, row)
            if rec_id:
                fields["id"] = rec_id
            obj = Model(**fields)
            db.add(obj)
            would_insert += 1

        elif mode == "clean":
            fields = apply_fn(existing, row)
            if existing:
                before = _model_to_dict(existing)
                for k, v in fields.items():
                    setattr(existing, k, v)
                db.flush()
                after = _model_to_dict(existing)
                write_audit(db, db_table_name, existing.id, "UPDATE", current_user.id, before, after, reason="CSV clean import")
                would_update += 1
            else:
                if rec_id:
                    fields["id"] = rec_id
                obj = Model(**fields)
                db.add(obj)
                db.flush()
                after = _model_to_dict(obj)
                write_audit(db, db_table_name, obj.id, "INSERT", current_user.id, None, after, reason="CSV clean import")
                would_insert += 1

    db.commit()
    return ImportResult(
        table=table, mode=mode,
        total_rows=len(rows),
        would_insert=would_insert, would_update=would_update, would_skip=would_skip,
        errors=errors, warnings=warnings, committed=True,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/preview", response_model=ImportResult)
async def preview_import(
    table: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    """Dry-run: validate CSV and return errors/warnings without writing to DB."""
    if table not in SUPPORTED_TABLES:
        raise HTTPException(400, f"不支援的資料表：{table}。支援：{', '.join(sorted(SUPPORTED_TABLES))}")
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "CSV 檔案為空或格式有誤")

    errors, warnings = VALIDATORS[table](rows, db)
    return _run_import(table, rows, errors, warnings, "dry_run", user, db)


@router.post("/supplement", response_model=ImportResult)
async def supplement_import(
    table: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    """Supplement: insert only rows with new IDs (skip existing). Does not require admin password."""
    if table not in SUPPORTED_TABLES:
        raise HTTPException(400, f"不支援的資料表：{table}。支援：{', '.join(sorted(SUPPORTED_TABLES))}")
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "CSV 檔案為空或格式有誤")

    errors, warnings = VALIDATORS[table](rows, db)
    if errors:
        raise HTTPException(422, detail={"message": f"CSV 含 {len(errors)} 個錯誤，請先修正後再匯入", "errors": errors})
    return _run_import(table, rows, errors, warnings, "supplement", user, db)


@router.post("/clean", response_model=ImportResult)
async def clean_import(
    table: str = Form(...),
    file: UploadFile = File(...),
    admin_password: str = Form(...),
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    """Clean (upsert): update existing + insert new. Requires admin password confirmation."""
    if table not in SUPPORTED_TABLES:
        raise HTTPException(400, f"不支援的資料表：{table}。支援：{', '.join(sorted(SUPPORTED_TABLES))}")
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "CSV 檔案為空或格式有誤")

    errors, warnings = VALIDATORS[table](rows, db)
    if errors:
        raise HTTPException(422, detail={"message": f"CSV 含 {len(errors)} 個錯誤，請先修正後再匯入", "errors": errors})
    return _run_import(table, rows, errors, warnings, "clean", user, db, admin_password=admin_password)
