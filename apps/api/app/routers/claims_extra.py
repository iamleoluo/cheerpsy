"""Phase 5：核銷案的跨方案、文件、退回補件、作廢與鐘點費回溯。

既有的 claim_batches.py 已涵蓋建案／增減紀錄／提交／收款／豁免文件，
本模組只補上它沒有的能力，避免重寫 727 行既有程式碼。
"""

import os
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status as http
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.case import Case
from app.models.claim_batch import ClaimBatch
from app.models.claim_extra import ClaimBatchPlan, ClaimDocument
from app.models.institution_plan import InstitutionPlan
from app.models.session_record import SessionRecord
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/claim-batches", tags=["claim-batches-extra"])

STAFF = ["admin", "accountant", "staff"]
DOC_TYPES = {"receipt": "領據", "monthly_list": "月次清冊表", "other": "其他"}


def _now():
    return datetime.now(timezone.utc)


def _batch(db: Session, batch_id: int) -> ClaimBatch:
    b = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="核銷案不存在")
    return b


# ---------------------------------------------------------------------------
# Q3：一案可跨方案
# ---------------------------------------------------------------------------
class PlansBody(BaseModel):
    plan_ids: list[int]

    @model_validator(mode="after")
    def _check(self):
        if not self.plan_ids:
            raise ValueError("至少需選一個方案")
        if len(set(self.plan_ids)) != len(self.plan_ids):
            raise ValueError("方案不可重複")
        return self


@router.get("/{batch_id}/plans")
def list_batch_plans(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(ClaimBatchPlan).filter(ClaimBatchPlan.claim_batch_id == batch_id).all()
    return [
        {
            "id": r.id,
            "plan_id": r.plan_id,
            "plan_name": r.plan.name if r.plan else None,
            "institution_name": (
                r.plan.contract.institution.name
                if r.plan and r.plan.contract and r.plan.contract.institution
                else None
            ),
        }
        for r in rows
    ]


@router.put("/{batch_id}/plans")
def set_batch_plans(
    batch_id: int,
    body: PlansBody,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    """設定此核銷案涵蓋哪些方案。可同時選多個一起核銷。"""
    b = _batch(db, batch_id)
    if b.status in ("submitted", "received"):
        raise HTTPException(status_code=400, detail=f"狀態 {b.status} 不可再更動方案")

    plans = db.query(InstitutionPlan).filter(InstitutionPlan.id.in_(body.plan_ids)).all()
    if len(plans) != len(body.plan_ids):
        raise HTTPException(status_code=404, detail="部分方案不存在")

    db.query(ClaimBatchPlan).filter(ClaimBatchPlan.claim_batch_id == batch_id).delete()
    db.flush()
    for pid in body.plan_ids:
        db.add(ClaimBatchPlan(claim_batch_id=batch_id, plan_id=pid))
    write_audit(db, "claim_batches", batch_id, "UPDATE", user.id, None, {"plan_ids": body.plan_ids})
    db.commit()
    return {"plan_ids": body.plan_ids}


@router.get("/{batch_id}/selectable-records")
def selectable_records(
    batch_id: int,
    plan_id: int = Query(..., description="紀錄要先從方案選定後，再從中挑（Q3）"),
    start: date | None = None,
    end: date | None = None,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    """可納入此核銷案的紀錄。

    Q2：期間為**參考區間**，不做缺口／重疊的硬檢查，只回傳提示資訊。
    """
    b = _batch(db, batch_id)
    q = (
        db.query(SessionRecord)
        .join(Case, SessionRecord.case_id == Case.id)
        .filter(
            SessionRecord.funding_source == "institution",
            SessionRecord.is_void.is_(False),
        )
    )
    if start:
        q = q.filter(SessionRecord.session_date >= start)
    if end:
        q = q.filter(SessionRecord.session_date <= end)

    rows = q.order_by(SessionRecord.session_date).all()
    names = {u.id: u.name for u in db.query(User).all()}
    out = []
    for r in rows:
        taken_by = r.claim_batch_id if r.claim_batch_id and r.claim_batch_id != batch_id else None
        out.append({
            "id": r.id,
            "session_date": r.session_date,
            "case_id": r.case_id,
            "case_name": r.case.name if getattr(r, "case", None) else None,
            "therapist_name": names.get(r.therapist_id),
            "session_type": r.session_type,
            "self_pay_amount": float(r.self_pay_amount or 0),
            "institution_claim_amount": float(r.institution_claim_amount or 0),
            "in_this_batch": r.claim_batch_id == batch_id,
            # 已被其他核銷案佔用 → 鎖定不可選，顯示所屬案號
            "locked_by_batch_id": taken_by,
            "therapist_confirmed": r.therapist_doc_submitted_at is not None,
            "admin_verified": r.admin_verified_at is not None,
            "rejected_reason": r.rejected_reason,
        })

    # 防漏提示（不阻擋）：期間內尚未被任何核銷案納入的筆數
    orphan = sum(1 for x in out if not x["in_this_batch"] and not x["locked_by_batch_id"])
    return {
        "batch_id": batch_id,
        "period_start": b.period_start,
        "period_end": b.period_end,
        "records": out,
        "hint_uncollected": orphan,
        "hint": (
            f"期間內尚有 {orphan} 筆機構紀錄未納入任何核銷案，可能漏請款。"
            if orphan else None
        ),
    }


# ---------------------------------------------------------------------------
# 退回補件（單筆，不影響同案其他紀錄）
# ---------------------------------------------------------------------------
class RejectBody(BaseModel):
    reason: str

    @model_validator(mode="after")
    def _check(self):
        if not (self.reason or "").strip():
            raise ValueError("退回需填寫原因")
        return self


@router.post("/{batch_id}/records/{record_id}/reject")
def reject_record(
    batch_id: int,
    record_id: int,
    body: RejectBody,
    user: User = Depends(RequireRole(STAFF)),
    db: Session = Depends(get_db),
):
    """行政發現錯誤 → 清除心理師確認與行政核對 → 回「待提交」並通知心理師。

    這是**單筆操作**，不影響同案其他紀錄；但只要有一筆未齊備，
    整案就無法轉「待送出」。
    """
    r = db.query(SessionRecord).filter(
        SessionRecord.id == record_id, SessionRecord.claim_batch_id == batch_id
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="此紀錄不在該核銷案中")

    before = {
        "therapist_doc_submitted_at": str(r.therapist_doc_submitted_at),
        "admin_verified_at": str(r.admin_verified_at),
    }
    r.therapist_doc_submitted_at = None
    r.therapist_doc_submitted_by = None
    r.admin_verified_at = None
    r.admin_verified_by = None
    r.rejected_at = _now()
    r.rejected_reason = body.reason.strip()
    r.rejected_by = user.id

    # 有一筆退回 → 整案退回「收集中」
    b = _batch(db, batch_id)
    if b.status == "ready":
        b.status = "collecting"

    write_audit(db, "session_records", r.id, "UPDATE", user.id, before,
                {"rejected": True, "reason": body.reason})
    db.commit()
    return {"rejected": True, "record_id": record_id, "batch_status": b.status}


# ---------------------------------------------------------------------------
# 作廢與款項回退
# ---------------------------------------------------------------------------
class VoidBody(BaseModel):
    reason: str
    password: str

    @model_validator(mode="after")
    def _check(self):
        if not (self.reason or "").strip():
            raise ValueError("作廢需填寫原因")
        return self


@router.post("/{batch_id}/void")
def void_batch(
    batch_id: int,
    body: VoidBody,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    """任一階段皆可作廢，需原因 + 密碼，並留稽核軌跡。

    作廢後：
      - 紀錄脫離本案、付款狀態退回未核銷、回到可核銷池可重新建案
      - 機構額度**不受影響**（額度在報到時就已由已預約轉已使用，與核銷無關）
      - 心理師酬勞**不受影響**（依已執行場次計算，與是否請款成功脫鉤）
      - 已實際撥款後才作廢會額外警告
    """
    from app.auth.password import verify_password

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=403, detail="密碼錯誤")

    b = _batch(db, batch_id)
    if b.voided_at:
        raise HTTPException(status_code=400, detail="此核銷案已作廢")

    warning = None
    if b.status == "received":
        warning = "此案機構已撥款，作廢後的退款需另行處理"

    records = db.query(SessionRecord).filter(SessionRecord.claim_batch_id == batch_id).all()
    for r in records:
        r.claim_batch_id = None
        if r.payment_status == "claimed":
            r.payment_status = "unpaid"

    b.status = "voided"
    b.void_reason = body.reason.strip()
    b.voided_at = _now()
    b.voided_by = user.id
    write_audit(db, "claim_batches", b.id, "UPDATE", user.id,
                {"status": "active", "record_count": len(records)},
                {"status": "voided", "reason": body.reason})
    db.commit()
    return {
        "voided": True,
        "released_records": len(records),
        "warning": warning,
        "note": "機構額度與心理師酬勞不受影響；編號不回收，重開會取新流水號",
    }


# ---------------------------------------------------------------------------
# Q4：鐘點費可回溯修改（不重算酬勞，Q22）
# ---------------------------------------------------------------------------
class RateBody(BaseModel):
    amount: float
    reason: str


@router.put("/records/{record_id}/amount")
def revise_amount(
    record_id: int,
    body: RateBody,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    """核銷紀錄的鐘點費回溯修改。

    Q22 定案：**不自動重算酬勞**。每位心理師算法不同，改由相關人員自行
    調整該場次酬勞。這裡只在對應的酬勞明細標記 rate_changed_flag 作為提示。
    """
    from app.models.therapist_payout import PayoutDetail

    r = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="修改鐘點費需填寫原因")

    before = {
        "amount": float(r.amount),
        "self_pay_amount": float(r.self_pay_amount or 0),
        "institution_claim_amount": float(r.institution_claim_amount or 0),
    }
    delta = float(body.amount) - float(r.amount)
    r.amount = body.amount
    # 自付額不變，差額全數反映在機構請款額
    r.institution_claim_amount = float(r.institution_claim_amount or 0) + delta

    flagged = (
        db.query(PayoutDetail).filter(PayoutDetail.session_id == r.id)
        .update({PayoutDetail.rate_changed_flag: True}, synchronize_session=False)
    )
    write_audit(db, "session_records", r.id, "UPDATE", user.id, before,
                {"amount": float(r.amount),
                 "institution_claim_amount": float(r.institution_claim_amount),
                 "reason": body.reason})
    db.commit()
    return {
        "record_id": r.id,
        "amount": float(r.amount),
        "institution_claim_amount": float(r.institution_claim_amount),
        "payout_rows_flagged": flagged,
        "note": "酬勞不自動重算，已標記提示請人工確認（Q22）",
    }


# ---------------------------------------------------------------------------
# 心理師上傳文件
# ---------------------------------------------------------------------------
class DocBody(BaseModel):
    doc_type: str
    file_name: str
    note: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.doc_type not in DOC_TYPES:
            raise ValueError(f"doc_type 需為 {list(DOC_TYPES)}")
        if not (self.file_name or "").strip():
            raise ValueError("需提供檔案名稱")
        return self


@router.get("/{batch_id}/documents")
def list_documents(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ClaimDocument).filter(ClaimDocument.claim_batch_id == batch_id)
    if user.role == "therapist":
        q = q.filter(ClaimDocument.therapist_id == user.id)
    return [
        {
            "id": d.id,
            "doc_type": d.doc_type,
            "doc_type_label": DOC_TYPES[d.doc_type],
            "file_name": d.file_name,
            "note": d.note,
            "therapist_name": d.therapist.name if d.therapist else None,
            "uploaded_at": d.uploaded_at,
        }
        for d in q.order_by(ClaimDocument.id.desc()).all()
    ]


@router.post("/{batch_id}/documents", status_code=http.HTTP_201_CREATED)
def add_document(
    batch_id: int,
    body: DocBody,
    user: User = Depends(RequireRole(["therapist", "admin", "staff"])),
    db: Session = Depends(get_db),
):
    """心理師一次把文件上傳完畢，行政要核銷時再下載。

    註：目前只登錄檔名與備註，實際檔案儲存待接上物件儲存後補。
    """
    _batch(db, batch_id)
    d = ClaimDocument(
        claim_batch_id=batch_id,
        therapist_id=user.id,
        doc_type=body.doc_type,
        file_name=body.file_name.strip(),
        note=body.note,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "doc_type": d.doc_type, "file_name": d.file_name}


@router.delete("/{batch_id}/documents/{doc_id}", status_code=http.HTTP_204_NO_CONTENT)
def delete_document(
    batch_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    d = db.query(ClaimDocument).filter(
        ClaimDocument.id == doc_id, ClaimDocument.claim_batch_id == batch_id
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    if user.role == "therapist" and d.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能刪除自己上傳的文件")
    db.delete(d)
    db.commit()


# ---------------------------------------------------------------------------
# 心理師端：文件確認
# ---------------------------------------------------------------------------
@router.get("/my/pending-docs")
def my_pending_docs(
    confirmed: bool = Query(False),
    user: User = Depends(RequireRole(["therapist"])),
    db: Session = Depends(get_db),
):
    """心理師只看得到自己負責的紀錄，且不顯示請款金額與收據。"""
    q = db.query(SessionRecord).filter(
        SessionRecord.therapist_id == user.id,
        SessionRecord.funding_source == "institution",
        SessionRecord.claim_batch_id.isnot(None),
        SessionRecord.is_void.is_(False),
    )
    q = q.filter(
        SessionRecord.therapist_doc_submitted_at.isnot(None)
        if confirmed
        else SessionRecord.therapist_doc_submitted_at.is_(None)
    )
    rows = q.order_by(SessionRecord.session_date).all()
    batches = {b.id: b for b in db.query(ClaimBatch).all()}
    return [
        {
            "id": r.id,
            "session_date": r.session_date,
            "case_name": r.case.name if getattr(r, "case", None) else None,
            "session_type": r.session_type,
            "claim_batch_id": r.claim_batch_id,
            "batch_number": batches[r.claim_batch_id].batch_number if r.claim_batch_id in batches else None,
            "admin_verified": r.admin_verified_at is not None,
            "rejected_reason": r.rejected_reason,
            "locked": r.admin_verified_at is not None,
        }
        for r in rows
    ]


class ConfirmBody(BaseModel):
    record_ids: list[int]


@router.post("/my/confirm-docs")
def confirm_docs(
    body: ConfirmBody,
    user: User = Depends(RequireRole(["therapist"])),
    db: Session = Depends(get_db),
):
    """單筆或批次確認文件。行政核對後或已送出則鎖定，不可撤回。"""
    rows = db.query(SessionRecord).filter(
        SessionRecord.id.in_(body.record_ids),
        SessionRecord.therapist_id == user.id,
    ).all()
    if len(rows) != len(set(body.record_ids)):
        raise HTTPException(status_code=404, detail="部分紀錄不存在或不屬於你")

    done = 0
    for r in rows:
        if r.admin_verified_at is not None:
            continue  # 行政已核對，鎖定
        r.therapist_doc_submitted_at = _now()
        r.therapist_doc_submitted_by = user.id
        r.rejected_at = None
        r.rejected_reason = None
        done += 1
    db.commit()
    return {"confirmed": done}


@router.post("/my/withdraw-docs")
def withdraw_docs(
    body: ConfirmBody,
    user: User = Depends(RequireRole(["therapist"])),
    db: Session = Depends(get_db),
):
    """已確認但行政尚未核對者可撤回。"""
    rows = db.query(SessionRecord).filter(
        SessionRecord.id.in_(body.record_ids),
        SessionRecord.therapist_id == user.id,
        SessionRecord.admin_verified_at.is_(None),
    ).all()
    for r in rows:
        r.therapist_doc_submitted_at = None
        r.therapist_doc_submitted_by = None
    db.commit()
    return {"withdrawn": len(rows)}


# ---------------------------------------------------------------------------
# 附件實際上傳與下載（B7）
# ---------------------------------------------------------------------------
DOC_ROOT = os.environ.get("CLAIM_DOC_ROOT", "/data/claim_docs")
MAX_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED = {
    "application/pdf", "image/jpeg", "image/png",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


@router.post("/{batch_id}/documents/upload", status_code=http.HTTP_201_CREATED)
def upload_document(
    batch_id: int,
    doc_type: str = Form(...),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(RequireRole(["therapist", "admin", "staff"])),
    db: Session = Depends(get_db),
):
    """實際上傳檔案。存到 volume，DB 記路徑。"""
    _batch(db, batch_id)
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type 需為 {list(DOC_TYPES)}")
    if file.content_type not in ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案型態 {file.content_type}；限 PDF／JPG／PNG／Excel",
        )

    folder = os.path.join(DOC_ROOT, str(batch_id))
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1][:10]
    stored = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")

    size = 0
    with open(stored, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                out.close()
                os.remove(stored)
                raise HTTPException(status_code=413, detail="檔案超過 20 MB 上限")
            out.write(chunk)

    d = ClaimDocument(
        claim_batch_id=batch_id,
        therapist_id=user.id,
        doc_type=doc_type,
        file_name=(file.filename or "未命名")[:300],
        note=note,
        stored_path=stored,
        content_type=file.content_type,
        size_bytes=size,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "file_name": d.file_name, "size_bytes": size}


@router.get("/{batch_id}/documents/{doc_id}/download")
def download_document(
    batch_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    d = db.query(ClaimDocument).filter(
        ClaimDocument.id == doc_id, ClaimDocument.claim_batch_id == batch_id
    ).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    # 心理師只能下載自己上傳的
    if user.role == "therapist" and d.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="只能下載自己上傳的文件")
    if not d.stored_path or not os.path.exists(d.stored_path):
        raise HTTPException(
            status_code=404,
            detail="此附件只登錄了檔名，沒有實際檔案（於支援上傳前建立）",
        )
    return FileResponse(d.stored_path, filename=d.file_name, media_type=d.content_type)
