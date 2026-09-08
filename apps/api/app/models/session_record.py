from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship as _rel

from app.database import Base


class SessionRecord(Base):
    __tablename__ = "session_records"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    session_date = Column(Date, nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_type = Column(String(20), nullable=False)
    # 諮商型態與地點的快照，跟著 appointment 複製過來（與 session_type 同一層級）
    consult_type = Column(String(20), nullable=True)
    location_kind = Column(String(20), nullable=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    fee_category = Column(String(20), nullable=False, default="counseling")
    amount = Column(Numeric(10, 2), nullable=False)
    payment_status = Column(String(20), nullable=False, default="unpaid")
    payment_method = Column(String(20), nullable=True)  # cash, transfer
    payment_note = Column(String(200), nullable=True)  # e.g. bank account last 5 digits
    paid_at = Column(DateTime(timezone=True), nullable=True)  # when payment was recorded
    claim_number = Column(String(100), nullable=True)
    receipt_number = Column(String(100), nullable=True)
    commission_rate_used = Column(Numeric(4, 2), nullable=True)
    funding_source = Column(String(20), nullable=True)  # snapshot of case.funding_source at materialization
    receipt_no = Column(String(30), nullable=True, unique=True)  # clinic receipt no: R{YYYYMMDD}{seq:04d}
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    discount_note = Column(String(200), nullable=True)
    is_void = Column(Boolean, nullable=False, default=False, server_default="false")
    void_reason = Column(String(200), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    voided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    claim_batch_id = Column(Integer, ForeignKey("claim_batches.id"), nullable=True)
    therapist_doc_submitted_at = Column(DateTime(timezone=True), nullable=True)
    therapist_doc_submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # 行政核對：心理師提交資料後，由行政再做一次資料正確性確認
    admin_verified_at = Column(DateTime(timezone=True), nullable=True)
    admin_verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    parent_record_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    outcall_bonus = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    outcall_note = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ── 機構合約子系統快照（複製自 appointments 上同名欄位，見 07 §4.2）──────
    # 為什麼在報到時「再複製一次」而不是只放在 appointments 上：這張表才是
    # 真正進日報表/月報表/核銷的事實列，快照要跟著它走，不跟著 appointment
    # 走（appointment 之後可能被改、被取消，session_record 一旦產生就不變）。
    # 已由 services/settlement.py 的 build_session_record() 在建立時複製。
    plan_id = Column(Integer, ForeignKey("inst_plans.id"), nullable=True)
    case_payable = Column(Numeric(10, 2), nullable=True)
    institution_payable = Column(Numeric(10, 2), nullable=True)
    compensation_mode = Column(String(12), nullable=True)  # commission | kickback | none
    commissionable_base = Column(Numeric(10, 2), nullable=True)
    plan_quote = Column(JSONB, nullable=True)

    # ── 櫃檯報到當場收款（個案自付額），與既有 payment_status 分開 ──────────
    # 為什麼不共用 payment_status：那個欄位對機構案的語意是「機構請款進度」
    # （unpaid→claiming→claimed，見 ledger.py:update_payment_status），跟
    # 「櫃檯今天有沒有收到個案自付額」是兩件事——硬共用會撞語意，把既有
    # 核銷案流程弄壞。這裡另開一組欄位，只代表「個案自付額今天收了沒」，
    # 自費案與機構案共用同一套（自費案的 case_payable 概念上就是全額）。
    # 判斷「這筆要收多少」：case_payable 有值就用它，否則 fallback 用 amount
    # （純自費/舊機構路徑沒有 case_payable，等於整筆都是個案自付）。
    copay_collected_at = Column(DateTime(timezone=True), nullable=True)
    copay_payment_method = Column(String(20), nullable=True)  # cash | transfer
    copay_payment_note = Column(String(200), nullable=True)

    appointment = _rel("Appointment", back_populates="session_record")
    claim_batch = _rel("ClaimBatch", foreign_keys=[claim_batch_id], lazy="select")
