from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.petty_cash import PettyCash
from app.models.user import User
from app.schemas.petty_cash import PettyCashCreate, PettyCashResponse
from app.services.audit import write_audit

router = APIRouter(prefix="/petty-cash", tags=["petty-cash"])


@router.get("", response_model=list[PettyCashResponse])
def list_petty_cash(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    records = db.query(PettyCash).order_by(desc(PettyCash.date), desc(PettyCash.id)).limit(200).all()
    return records


@router.post("", response_model=PettyCashResponse, status_code=status.HTTP_201_CREATED)
def create_petty_cash(
    body: PettyCashCreate,
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    last = db.query(PettyCash).order_by(desc(PettyCash.id)).first()
    current_balance = float(last.balance_after) if last else 0.0
    new_balance = current_balance + body.amount

    record = PettyCash(
        date=body.date,
        amount=body.amount,
        category=body.category,
        description=body.description,
        receipt_note=body.receipt_note,
        balance_after=new_balance,
        created_by=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_petty_cash(
    record_id: int,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    record = db.query(PettyCash).filter(PettyCash.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    write_audit(db, "petty_cash", record.id, "DELETE", user.id,
                {"date": str(record.date), "amount": float(record.amount), "description": record.description},
                None)
    db.delete(record)
    db.commit()
