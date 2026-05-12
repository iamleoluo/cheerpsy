from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.database import get_db
from app.models.case import Case
from app.models.user import User
from app.schemas.case import CaseCreate, CaseResponse, CaseUpdate
from app.utils.encryption import encrypt_national_id, hmac_national_id

router = APIRouter(prefix="/cases", tags=["cases"])


def _to_response(c: Case) -> CaseResponse:
    return CaseResponse(
        id=c.id,
        case_code=c.case_code,
        name=c.name,
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
        notes=c.notes,
    )


@router.get("", response_model=list[CaseResponse])
def list_cases(
    status_filter: str | None = Query(None, alias="status"),
    therapist_id: int | None = None,
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Case)
    if user.role == "therapist":
        query = query.filter(Case.therapist_id == user.id)
    elif therapist_id:
        query = query.filter(Case.therapist_id == therapist_id)
    if status_filter:
        query = query.filter(Case.status == status_filter)
    if q:
        query = query.filter(Case.name.ilike(f"%{q}%"))
    cases = query.order_by(Case.id.desc()).all()
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
    c = Case(
        name=body.name,
        birth_date=body.birth_date,
        gender=body.gender,
        phone=body.phone,
        emergency_contact=body.emergency_contact,
        initial_visit_date=body.initial_visit_date,
        funding_source=body.funding_source,
        institution_id=body.institution_id if body.funding_source == "institution" else None,
        therapist_id=body.therapist_id if user.role != "therapist" else user.id,
        notes=body.notes,
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
    user: User = Depends(RequireRole(["admin", "accountant"])),
    db: Session = Depends(get_db),
):
    c = db.query(Case).filter(Case.id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    update_data = body.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(c, key, val)
    if c.funding_source == "self_pay":
        c.institution_id = None
    db.commit()
    db.refresh(c)
    return _to_response(c)
