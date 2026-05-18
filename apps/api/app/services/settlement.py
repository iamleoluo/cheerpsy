"""Real-time settlement: appointments whose end time has passed -> executed + session_records.

Lazy materialization: called on ledger reads. Any booked appointment whose end
time (upper bound of time_range) is <= now is converted into a SessionRecord.
Commission rate and funding source are snapshotted at materialization time
(i.e. the bill-generation moment), reading the *current* User/Case values.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.case import Case
from app.models.session_record import SessionRecord
from app.models.user import User

DEFAULT_COMMISSION_RATE = Decimal("0.70")


def next_receipt_no(db: Session, d: date) -> str:
    """Clinic-wide receipt number: R{YYYYMMDD}{seq:04d} (seq per session_date)."""
    count = (
        db.query(SessionRecord)
        .filter(SessionRecord.session_date == d)
        .count()
    )
    return f"R{d.strftime('%Y%m%d')}{count + 1:04d}"


def materialize_due_appointments(db: Session, up_to: datetime | None = None) -> dict:
    """Convert all booked appointments whose end time has passed into session records."""
    if up_to is None:
        up_to = datetime.now(timezone.utc)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.status == "booked",
            text("upper(time_range) <= :u").bindparams(u=up_to),
        )
        .all()
    )

    therapist_cache: dict[int, User] = {}
    case_cache: dict[int, Case] = {}
    materialized = 0
    skipped = 0

    for appt in appointments:
        existing = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
        if existing:
            skipped += 1
            continue

        if appt.therapist_id not in therapist_cache:
            therapist_cache[appt.therapist_id] = (
                db.query(User).filter(User.id == appt.therapist_id).first()
            )
        therapist = therapist_cache[appt.therapist_id]

        if appt.case_id not in case_cache:
            case_cache[appt.case_id] = (
                db.query(Case).filter(Case.id == appt.case_id).first()
            )
        case = case_cache[appt.case_id]

        rate = DEFAULT_COMMISSION_RATE
        if therapist and therapist.commission_rate is not None:
            rate = Decimal(str(therapist.commission_rate))

        funding = case.funding_source if case else "self_pay"
        session_date = appt.time_range.lower.date()

        appt.status = "executed"
        record = SessionRecord(
            appointment_id=appt.id,
            session_date=session_date,
            case_id=appt.case_id,
            therapist_id=appt.therapist_id,
            session_type=appt.session_type,
            room_id=appt.room_id,
            fee_category="counseling",
            amount=appt.amount,
            commission_rate_used=rate,
            funding_source=funding,
            receipt_no=next_receipt_no(db, session_date),
            payment_status="unpaid",
        )
        db.add(record)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            skipped += 1
            continue
        materialized += 1

    db.commit()
    return {"materialized": materialized, "skipped": skipped}


def run_daily_settlement(db: Session, target_date: date | None = None) -> dict:
    """Backward-compatible wrapper for POST /ledger/settle.

    Settles everything up to the end of target_date (or now if not given).
    """
    if target_date is None:
        up_to = datetime.now(timezone.utc)
        label = str(date.today())
    else:
        up_to = datetime(
            target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc
        ) + timedelta(days=1)
        label = str(target_date)
    result = materialize_due_appointments(db, up_to)
    return {
        "date": label,
        "executed": result["materialized"],
        "skipped": result["skipped"],
    }
