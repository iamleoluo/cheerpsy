"""T+1 daily settlement: booked appointments from yesterday → executed + session_records."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.session_record import SessionRecord


def run_daily_settlement(db: Session, target_date: date | None = None) -> dict:
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    range_filter = f"[{day_start.isoformat()},{day_end.isoformat()})"

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.status == "booked",
            text("time_range && :r").bindparams(r=range_filter),
        )
        .all()
    )

    executed = 0
    skipped = 0

    for appt in appointments:
        existing = db.query(SessionRecord).filter(SessionRecord.appointment_id == appt.id).first()
        if existing:
            skipped += 1
            continue

        appt.status = "executed"

        record = SessionRecord(
            appointment_id=appt.id,
            session_date=target_date,
            case_id=appt.case_id,
            therapist_id=appt.therapist_id,
            session_type=appt.session_type,
            room_id=appt.room_id,
            fee_category="counseling",
            amount=appt.amount,
            payment_status="unpaid",
        )
        db.add(record)
        executed += 1

    db.commit()
    return {"date": str(target_date), "executed": executed, "skipped": skipped}
