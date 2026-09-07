from app.models.user import User
from app.models.institution import Institution
from app.models.case import Case
from app.models.couple_member import CoupleMember
from app.models.room import Room
from app.models.appointment import Appointment
from app.models.session_record import SessionRecord
from app.models.invoice import Invoice
from app.models.therapist_payout import TherapistPayout, PayoutDetail
from app.models.petty_cash import PettyCash
from app.models.audit_log import AuditLog
from app.models.reminder_log import ReminderLog
from app.models.invitation import Invitation
from app.models.claim_batch import ClaimBatch
from app.models.product_sales import ProductSale
from app.models.case_institution_quota import CaseInstitutionQuota
from app.models.quota_template import QuotaTemplate
# P0 修正：這支原本漏了 Notification，導致 alembic/env.py 的
# `from app.models import *` 抓不到 notifications 表，下次 autogenerate
# 會產生 op.drop_table("notifications")。見 V2升級計畫 01 §C7。
from app.models.notification import Notification
# P1 出席驅動·報到三步驟（01 §A2、02 §1.2）：收費項目主檔、收據。
from app.models.fee_item import FeeItem
from app.models.receipt import Receipt
# 機構合約子系統的資料表也集中在這裡註冊（models 位於 app/institution/models/，
# 但註冊點統一放此處，避免有人漏掉、重蹈 Notification 的覆轍）。
from app.institution.models import (  # noqa: F401
    InstContract,
    InstPlan,
    InstRateRule,
    InstQuotaPool,
    InstEnrollment,
    InstClaimCase,
    InstClaimLine,
)

__all__ = [
    "User",
    "Institution",
    "Case",
    "CoupleMember",
    "Room",
    "Appointment",
    "SessionRecord",
    "Invoice",
    "TherapistPayout",
    "PayoutDetail",
    "PettyCash",
    "AuditLog",
    "ReminderLog",
    "Invitation",
    "ClaimBatch",
    "ProductSale",
    "CaseInstitutionQuota",
    "QuotaTemplate",
    "Notification",
    "FeeItem",
    "Receipt",
    "InstContract",
    "InstPlan",
    "InstRateRule",
    "InstQuotaPool",
    "InstEnrollment",
    "InstClaimCase",
    "InstClaimLine",
]
