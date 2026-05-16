from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.invoice import InvoiceCreate, InvoiceResponse, InvoiceVoid

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _make_invoice_number(therapist_code: str, dt: datetime, db: Session) -> str:
    from sqlalchemy import text

    date_str = dt.strftime("%Y%m%d")
    prefix = f"I-{date_str}-{therapist_code}-"
    count = db.execute(
        text("SELECT COUNT(*) FROM invoices WHERE invoice_number LIKE :p"),
        {"p": f"{prefix}%"},
    ).scalar()
    seq = (count or 0) + 1
    return f"{prefix}{seq:03d}"


def _to_response(inv: Invoice) -> InvoiceResponse:
    appt = inv.appointment
    return InvoiceResponse(
        id=inv.id,
        invoice_number=inv.invoice_number,
        appointment_id=inv.appointment_id,
        appointment_number=appt.appointment_number if appt else None,
        case_name=appt.case.name if appt and appt.case else None,
        therapist_name=appt.therapist.name if appt and appt.therapist else None,
        amount=float(appt.amount) if appt else None,
        status=inv.status,
        void_reason=inv.void_reason,
        created_at=inv.created_at,
    )


@router.get("", response_model=list[InvoiceResponse])
def list_invoices(
    status_filter: str | None = Query(None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Invoice).join(Appointment)
    if user.role == "therapist":
        query = query.filter(Appointment.therapist_id == user.id)
    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    invoices = query.order_by(Invoice.id.desc()).limit(200).all()
    return [_to_response(i) for i in invoices]


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(
    body: InvoiceCreate,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    appt = db.query(Appointment).filter(Appointment.id == body.appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status != "executed":
        raise HTTPException(status_code=400, detail="Appointment must be executed first")

    existing = db.query(Invoice).filter(
        Invoice.appointment_id == body.appointment_id,
        Invoice.status == "active",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Active invoice already exists")

    therapist = appt.therapist
    code = therapist.user_code if therapist else "XXX"
    number = _make_invoice_number(code, appt.created_at, db)

    inv = Invoice(
        invoice_number=number,
        appointment_id=body.appointment_id,
        status="active",
        created_by=user.id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _to_response(inv)


@router.put("/{invoice_id}/void", response_model=InvoiceResponse)
def void_invoice(
    invoice_id: int,
    body: InvoiceVoid,
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status == "voided":
        raise HTTPException(status_code=400, detail="Already voided")
    inv.status = "voided"
    inv.void_reason = body.void_reason
    db.commit()
    db.refresh(inv)
    return _to_response(inv)
