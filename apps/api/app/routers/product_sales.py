import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole
from app.database import get_db
from app.models.product_sales import ProductSale
from app.models.user import User
from app.schemas.product_sales import (
    ProductSaleCreate,
    ProductSaleResponse,
    ProductSaleUpdate,
    ProductSaleVoid,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/product-sales", tags=["product-sales"])

ROLES = ["admin", "accountant", "staff"]


def _next_receipt_no(db: Session, d: date) -> str:
    count = db.query(ProductSale).filter(ProductSale.sale_date == d).count()
    return f"P{d.strftime('%Y%m%d')}{count + 1:04d}"


def _to_response(p: ProductSale) -> ProductSaleResponse:
    return ProductSaleResponse(
        id=p.id,
        sale_date=p.sale_date,
        product_name=p.product_name,
        amount=float(p.amount),
        quantity=p.quantity,
        payment_method=p.payment_method,
        payment_note=p.payment_note,
        receipt_no=p.receipt_no,
        is_void=bool(p.is_void),
        void_reason=p.void_reason,
        created_at=p.created_at.isoformat() if p.created_at else None,
    )


@router.get("", response_model=list[ProductSaleResponse])
def list_product_sales(
    month: str | None = Query(None, description="YYYY-MM"),
    include_void: bool = Query(False),
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(ProductSale)
    if not include_void:
        q = q.filter(ProductSale.is_void.is_(False))
    if month:
        try:
            year, mon = int(month[:4]), int(month[5:7])
            last_day = calendar.monthrange(year, mon)[1]
            q = q.filter(
                ProductSale.sale_date >= date(year, mon, 1),
                ProductSale.sale_date <= date(year, mon, last_day),
            )
        except (ValueError, IndexError):
            pass
    return [_to_response(p) for p in q.order_by(ProductSale.sale_date.desc(), ProductSale.id.desc()).all()]


@router.post("", response_model=ProductSaleResponse)
def create_product_sale(
    body: ProductSaleCreate,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    p = ProductSale(
        sale_date=body.sale_date,
        product_name=body.product_name.strip(),
        amount=body.amount,
        quantity=body.quantity,
        payment_method=body.payment_method or "cash",
        payment_note=body.payment_note.strip() if body.payment_note else None,
        receipt_no=_next_receipt_no(db, body.sale_date),
        created_by=user.id,
    )
    db.add(p)
    db.flush()
    write_audit(db, "product_sales", p.id, "CREATE", user.id, None, {"product_name": p.product_name, "amount": float(p.amount)})
    db.commit()
    db.refresh(p)
    return _to_response(p)


@router.put("/{sale_id}", response_model=ProductSaleResponse)
def update_product_sale(
    sale_id: int,
    body: ProductSaleUpdate,
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    p = db.query(ProductSale).filter(ProductSale.id == sale_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Sale not found")
    if p.is_void:
        raise HTTPException(status_code=400, detail="已作廢不可修改")
    before = {"product_name": p.product_name, "amount": float(p.amount), "quantity": p.quantity}
    if body.sale_date is not None:
        p.sale_date = body.sale_date
    if body.product_name is not None:
        p.product_name = body.product_name.strip()
    if body.amount is not None:
        p.amount = body.amount
    if body.quantity is not None:
        p.quantity = body.quantity
    if body.payment_method is not None:
        p.payment_method = body.payment_method
    if body.payment_note is not None:
        p.payment_note = body.payment_note.strip() or None
    after = {"product_name": p.product_name, "amount": float(p.amount), "quantity": p.quantity}
    write_audit(db, "product_sales", p.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(p)
    return _to_response(p)


@router.put("/{sale_id}/void", response_model=ProductSaleResponse)
def void_product_sale(
    sale_id: int,
    body: ProductSaleVoid = ProductSaleVoid(),
    user: User = Depends(RequireRole(ROLES)),
    db: Session = Depends(get_db),
):
    p = db.query(ProductSale).filter(ProductSale.id == sale_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Sale not found")
    if p.is_void:
        raise HTTPException(status_code=400, detail="已作廢")
    p.is_void = True
    p.void_reason = body.reason.strip() if body.reason else None
    write_audit(db, "product_sales", p.id, "VOID", user.id, {"is_void": False}, {"is_void": True}, reason=p.void_reason)
    db.commit()
    db.refresh(p)
    return _to_response(p)
