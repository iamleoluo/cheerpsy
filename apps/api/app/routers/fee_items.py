from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.fee_item import FeeItem
from app.models.user import User

router = APIRouter(prefix="/fee-items", tags=["fee-items"])


class FeeItemResponse(BaseModel):
    id: int
    name: str
    is_default: bool
    sort_order: int

    model_config = {"from_attributes": True}


@router.get("", response_model=list[FeeItemResponse])
def list_fee_items(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """報到流程步驟3：開立收據的收款項目下拉來源。見 models/fee_item.py。"""
    return (
        db.query(FeeItem)
        .filter(FeeItem.is_active.is_(True))
        .order_by(FeeItem.sort_order)
        .all()
    )
