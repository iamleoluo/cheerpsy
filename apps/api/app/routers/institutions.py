from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.institution import Institution
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/institutions", tags=["institutions"])


class InstitutionCreate(BaseModel):
    name: str
    code: str | None = None


class InstitutionUpdate(BaseModel):
    name: str | None = None
    code: str | None = None


class InstitutionResponse(BaseModel):
    id: int
    name: str
    code: str | None = None
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
            if body.code:
                existing.code = body.code.strip().upper()
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Institution already exists")

    if body.code:
        code = body.code.strip().upper()
        if len(code) > 5:
            raise HTTPException(status_code=400, detail="Code must be 5 characters or less")
        dup = db.query(Institution).filter(Institution.code == code).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Code '{code}' already in use")
    else:
        code = None

    inst = Institution(name=body.name.strip(), code=code, created_by=user.id)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.put("/{inst_id}", response_model=InstitutionResponse)
def update_institution(
    inst_id: int,
    body: InstitutionUpdate,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    inst = db.query(Institution).filter(Institution.id == inst_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    before_data = {"name": inst.name, "code": inst.code}
    if body.name is not None:
        inst.name = body.name.strip()
    if body.code is not None:
        code = body.code.strip().upper()
        if len(code) > 5:
            raise HTTPException(status_code=400, detail="Code must be 5 characters or less")
        dup = db.query(Institution).filter(Institution.code == code, Institution.id != inst_id).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Code '{code}' already in use")
        inst.code = code
    after_data = {"name": inst.name, "code": inst.code}
    write_audit(db, "institutions", inst.id, "UPDATE", user.id, before_data, after_data)
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
    write_audit(db, "institutions", inst.id, "UPDATE", user.id,
                {"is_active": True}, {"is_active": False})
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
    write_audit(db, "institutions", inst.id, "UPDATE", user.id,
                {"is_active": False}, {"is_active": True})
    db.commit()
    db.refresh(inst)
    return inst
