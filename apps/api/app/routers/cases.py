from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.case import Case
from app.models.user import User
from app.schemas.case import CaseCreate, CaseResponse, CaseUpdate
from app.services.audit import write_audit
from app.services.case_numbering import generate_case_number
from app.utils.encryption import encrypt_national_id, hmac_national_id

router = APIRouter(prefix="/cases", tags=["cases"])


def _to_response(c: Case) -> CaseResponse:
    return CaseResponse(
        id=c.id,
        temp_seq=c.temp_seq,
        case_code=c.case_code,
        case_number=c.case_number,
        name=c.name,
        age=c.age,
        birth_date=c.birth_date,
        gender=c.gender,
        phone=c.phone,
        phone_home=c.phone_home,
        address=c.address,
        emergency_contact=c.emergency_contact,
        emergency_phone=c.emergency_phone,
        emergency_phone2=c.emergency_phone2,
        initial_visit_date=c.initial_visit_date,
        funding_source=c.funding_source,
        institution_id=c.institution_id,
        institution_name=c.institution.name if c.institution else None,
        referral_source=c.referral_source,
        session_location=c.session_location,
        therapist_id=c.therapist_id,
        therapist_name=c.therapist.name if c.therapist else None,
        status=c.status,
        billing_cycle=c.billing_cycle,
        has_national_id=c.national_id_encrypted is not None,
        notes=c.notes,
    )


@router.get("", response_model=list[CaseResponse])
def list_cases(
    status_filter: str | None = Query(None, alias="status"),
    therapist_id: int | None = None,
    billing_cycle: str | None = Query(None, description="once / monthly / multiple"),
    q: str | None = Query(None, description="搜尋個案姓名 / 案號 / 心理師姓名"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Case).options(joinedload(Case.therapist), joinedload(Case.institution))
    if user.role == "therapist":
        query = query.filter(Case.therapist_id == user.id)
    elif therapist_id:
        query = query.filter(Case.therapist_id == therapist_id)
    if status_filter:
        query = query.filter(Case.status == status_filter)
    if billing_cycle:
        query = query.filter(Case.billing_cycle == billing_cycle)
    if q:
        # 統一搜尋：個案姓名 / 案號（temp + 正式）/ 心理師姓名
        like = f"%{q}%"
        query = query.outerjoin(Case.therapist).filter(
            or_(
                Case.name.ilike(like),
                Case.case_number.ilike(like),
                Case.case_code.ilike(like),
                User.name.ilike(like),
            )
        )
    cases = query.order_by(Case.id.desc()).limit(500).all()
    return [_to_response(c) for c in cases]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role == "therapist" and c.therapist_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return _to_response(c)


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    body: CaseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    next_seq = (db.query(func.coalesce(func.max(Case.temp_seq), 0)).scalar() or 0) + 1

    c = Case(
        temp_seq=next_seq,
        name=body.name,
        age=body.age,
        birth_date=body.birth_date,
        gender=body.gender,
        phone=body.phone,
        emergency_contact=body.emergency_contact,
        initial_visit_date=body.initial_visit_date,
        funding_source=body.funding_source,
        institution_id=body.institution_id if body.funding_source == "institution" else None,
        therapist_id=body.therapist_id if user.role != "therapist" else user.id,
        billing_cycle=body.billing_cycle,
        notes=body.notes,
        created_by=user.id,
    )
    if body.national_id:
        c.national_id_encrypted = encrypt_national_id(body.national_id)
        c.national_id_hmac = hmac_national_id(body.national_id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _to_response(c)


@router.put("/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: int,
    body: CaseUpdate,
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    update_data = body.model_dump(exclude_unset=True)

    if "national_id" in update_data:
        nid = update_data.pop("national_id")
        if nid:
            c.national_id_encrypted = encrypt_national_id(nid)
            c.national_id_hmac = hmac_national_id(nid)

    if c.case_number and "case_number" in update_data:
        raise HTTPException(status_code=400, detail="Case number cannot be changed once assigned")

    before = {k: getattr(c, k, None) for k in update_data.keys()}
    for key, val in update_data.items():
        setattr(c, key, val)
    if c.funding_source == "self_pay":
        c.institution_id = None
    after = {k: getattr(c, k, None) for k in update_data.keys()}
    write_audit(db, "cases", c.id, "UPDATE", user.id, before, after)
    db.commit()
    db.refresh(c)
    return _to_response(c)


@router.post("/{case_id}/activate", response_model=CaseResponse)
def activate_case(
    case_id: int,
    user: User = Depends(RequireRole(["admin", "accountant", "staff"])),
    db: Session = Depends(get_db),
):
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    if c.case_number:
        raise HTTPException(status_code=400, detail="Case already has a formal number")
    if c.status != "initial":
        raise HTTPException(status_code=400, detail="Only initial-status cases can be activated")

    missing = []
    if not c.national_id_encrypted:
        missing.append("身份證字號")
    if not c.birth_date:
        missing.append("出生日期")
    if not c.phone:
        missing.append("連絡電話")
    if missing:
        raise HTTPException(status_code=400, detail=f"轉正式前需填寫：{'、'.join(missing)}")

    c.case_number = generate_case_number(db, c)
    c.status = "ongoing"
    write_audit(db, "cases", c.id, "UPDATE", user.id,
                {"status": "initial", "case_number": None},
                {"status": "ongoing", "case_number": c.case_number})
    db.commit()
    db.refresh(c)
    return _to_response(c)
