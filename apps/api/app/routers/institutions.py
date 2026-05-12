from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.institution import Institution
from app.models.user import User

router = APIRouter(prefix="/institutions", tags=["institutions"])


class InstitutionCreate(BaseModel):
    name: str


class InstitutionResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[InstitutionResponse])
def list_institutions(
    include_inactive: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Institution)
    if not include_inactive:
        query = query.filter(Institution.is_active == True)
    return query.order_by(Institution.name).all()


@router.post("", response_model=InstitutionResponse, status_code=status.HTTP_201_CREATED)
def create_institution(
    body: InstitutionCreate,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    existing = db.query(Institution).filter(Institution.name == body.name.strip()).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Institution already exists")
    inst = Institution(name=body.name.strip())
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.delete("/{inst_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_institution(
    inst_id: int,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    inst.is_active = False
    db.commit()


@router.put("/{inst_id}/activate", response_model=InstitutionResponse)
def activate_institution(
    inst_id: int,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    inst.is_active = True
    db.commit()
    db.refresh(inst)
    return inst
