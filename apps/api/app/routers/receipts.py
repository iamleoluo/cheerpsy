"""收據開立 Router

GET  /receipts/single-session/{record_id}/preview  → ReceiptPreview JSON
POST /receipts/single-session/{record_id}           → PDF bytes

GET  /receipts/batch/{batch_id}/preview             → ReceiptPreview JSON
POST /receipts/batch/{batch_id}                     → PDF bytes

GET  /receipts/product/{sale_id}/preview            → ReceiptPreview JSON
POST /receipts/product/{sale_id}                    → PDF bytes
"""
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.claim_batch import ClaimBatch
from app.models.case import Case
from app.models.institution import Institution
from app.models.product_sales import ProductSale
from app.models.session_record import SessionRecord
from app.models.user import User
from app.schemas.receipt import MultiItemReceiptPreview, MultiItemReceiptRequest, ReceiptItem, ReceiptPreview, ReceiptRequest
from app.services.pdf.receipt import (
    MultiItemReceiptData,
    ReceiptData,
    build_institution_receipt,
    build_multi_session_receipt,
    build_product_receipt,
    build_self_pay_batch_receipt,
    build_single_session_receipt,
    render_multi_item_receipt,
    render_receipt,
)

router = APIRouter(prefix="/receipts", tags=["receipts"])

ROLES = ["admin", "accountant", "staff"]


def _preview_from_data(data: ReceiptData, show_tax_id: bool = False) -> ReceiptPreview:
    return ReceiptPreview(
        receipt_number=data.receipt_number,
        issue_date=data.issue_date,
        payee=data.payee,
        fee_category=data.fee_category,
        quantity_label=data.quantity_label,
        quantity=data.quantity,
        total_amount=data.total_amount,
        note=data.note,
        show_tax_id=show_tax_id,
        session_type_label=data.session_type_label,
    )


def _build_record_dicts(db: Session, batch_id: int) -> list[dict]:
    records = (
        db.query(SessionRecord)
        .filter(SessionRecord.claim_batch_id == batch_id, SessionRecord.is_void.is_(False))
        .order_by(SessionRecord.session_date)
        .all()
    )
    return [
        {
            "session_date": r.session_date,
            "amount": float(r.amount),
        }
        for r in records
    ]


# ── 單次諮商 ────────────────────────────────────────────────────────────────

@router.get("/single-session/{record_id}/preview", response_model=ReceiptPreview)
def preview_single_session(
    record_id: int,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    record = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Session record not found")
    case = db.query(Case).filter(Case.id == record.case_id).first() if record.case_id else None
    data = build_single_session_receipt(record, case)
    return _preview_from_data(data, show_tax_id=False)


@router.post("/single-session/{record_id}")
def issue_single_session(
    record_id: int,
    body: ReceiptRequest,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    record = db.query(SessionRecord).filter(SessionRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Session record not found")
    data = ReceiptData(**body.model_dump())
    pdf_bytes = render_receipt(data)
    filename = f"receipt-{body.receipt_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 核銷案（自費多次 / 機構）───────────────────────────────────────────────

@router.get("/batch/{batch_id}/preview", response_model=ReceiptPreview)
def preview_batch(
    batch_id: int,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")

    records = _build_record_dicts(db, batch_id)

    if batch.type == "self_pay":
        case = db.query(Case).filter(Case.id == batch.case_id).first() if batch.case_id else None
        data = build_multi_session_receipt(batch, case, records)
        return _preview_from_data(data, show_tax_id=False)
    else:
        inst = (
            db.query(Institution).filter(Institution.id == batch.institution_id).first()
            if batch.institution_id
            else None
        )
        data = build_institution_receipt(batch, inst, records)
        return _preview_from_data(data, show_tax_id=True)


@router.post("/batch/{batch_id}")
def issue_batch(
    batch_id: int,
    body: ReceiptRequest,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    data = ReceiptData(**body.model_dump())
    pdf_bytes = render_receipt(data)
    filename = f"receipt-{body.receipt_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 商品販售 ────────────────────────────────────────────────────────────────

@router.get("/product/{sale_id}/preview", response_model=ReceiptPreview)
def preview_product(
    sale_id: int,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    sale = db.query(ProductSale).filter(ProductSale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Product sale not found")
    data = build_product_receipt(sale)
    return _preview_from_data(data, show_tax_id=False)


@router.post("/product/{sale_id}")
def issue_product(
    sale_id: int,
    body: ReceiptRequest,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    sale = db.query(ProductSale).filter(ProductSale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Product sale not found")
    data = ReceiptData(**body.model_dump())
    pdf_bytes = render_receipt(data)
    filename = f"receipt-{body.receipt_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 自費批次整體收據 ──────────────────────────────────────────────────────────

@router.get("/self-pay-batch/{batch_id}/preview", response_model=MultiItemReceiptPreview)
def preview_self_pay_batch(
    batch_id: int,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    from app.models.session_record import SessionRecord as SR
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    case = db.query(Case).filter(Case.id == batch.case_id).first() if batch.case_id else None
    records = (
        db.query(SR)
        .filter(SR.claim_batch_id == batch_id, SR.is_void.is_(False))
        .order_by(SR.session_date)
        .all()
    )
    data = build_self_pay_batch_receipt(batch, case, records)
    return MultiItemReceiptPreview(
        receipt_number=data.receipt_number,
        issue_date=data.issue_date,
        payee=data.payee,
        fee_category=data.fee_category,
        items=[ReceiptItem(**item) for item in data.items],
        total_amount=data.total_amount,
        note=data.note,
        show_tax_id=False,
    )


@router.post("/self-pay-batch/{batch_id}")
def issue_self_pay_batch(
    batch_id: int,
    body: MultiItemReceiptRequest,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    batch = db.query(ClaimBatch).filter(ClaimBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Claim batch not found")
    data = MultiItemReceiptData(
        receipt_number=body.receipt_number,
        issue_date=body.issue_date,
        payee=body.payee,
        fee_category=body.fee_category,
        items=[item.model_dump() for item in body.items],
        total_amount=body.total_amount,
        note=body.note,
        tax_id=body.tax_id,
    )
    pdf_bytes = render_multi_item_receipt(data)
    filename = f"receipt-{body.receipt_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
