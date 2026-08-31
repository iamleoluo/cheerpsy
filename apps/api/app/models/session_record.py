from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship as _rel

from app.database import Base


class SessionRecord(Base):
    __tablename__ = "session_records"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)  # 收據單一真相（Phase 1b 起為權威來源）
    daily_closing_id = Column(Integer, ForeignKey("daily_closings.id"), nullable=True, index=True)
    # 補收款：自動回寫月報表該日，標小字「MM/DD 補收 $X」，不需解鎖、不列覆核
    supplementary_paid_at = Column(DateTime(timezone=True), nullable=True)
    session_date = Column(Date, nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_type = Column(String(20), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    fee_category = Column(String(20), nullable=False, default="counseling")
    # amount = 總額；下面兩欄是它的拆分（self_pay + institution_claim = amount）
    amount = Column(Numeric(10, 2), nullable=False)
    self_pay_amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    institution_claim_amount = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    # 追款方式（應收帳冊三分頁依此分）：immediate 未收／monthly 月結／institution 機構
    payment_track = Column(String(20), nullable=False, default="immediate", server_default="immediate")
    fee_item = Column(String(30), nullable=True)  # 諮商項目，連動收據名目
    is_no_show = Column(Boolean, nullable=False, default=False, server_default="false")
    no_show_fee = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    payment_status = Column(String(20), nullable=False, default="unpaid")
    payment_method = Column(String(20), nullable=True)  # cash, transfer
    payment_note = Column(String(200), nullable=True)  # e.g. bank account last 5 digits
    paid_at = Column(DateTime(timezone=True), nullable=True)  # when payment was recorded
    claim_number = Column(String(100), nullable=True)
    receipt_number = Column(String(100), nullable=True)
    commission_rate_used = Column(Numeric(4, 2), nullable=True)
    funding_source = Column(String(20), nullable=True)  # snapshot of case.funding_source at materialization
    # DEPRECATED：收據單一真相已移至 invoices，請改讀 invoice_id。
    # 所有讀取端已切換（/daily、/ar、export、PDF）。欄位仍保留，因為它存著
    # 歷史 R 格式收據號，且 data_import 的既有資料仍靠它比對；
    # 實際 DROP 應排在正式資料遷移（Stage 2）完成並核對後。
    receipt_no = Column(String(30), nullable=True, unique=True)
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
    # 退回補件（Phase 5）：清除心理師確認與行政核對，回「待提交」
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_reason = Column(String(500), nullable=True)
    rejected_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    parent_record_id = Column(Integer, ForeignKey("session_records.id"), nullable=True)
    outcall_bonus = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    outcall_note = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    appointment = _rel("Appointment", back_populates="session_record")
    # invoices.session_record_id 與本表 invoice_id 互指，需明確指定 join 路徑
    invoice = _rel("Invoice", foreign_keys=[invoice_id], lazy="joined")
    case = _rel("Case", foreign_keys=[case_id], lazy="joined")
    claim_batch = _rel("ClaimBatch", foreign_keys=[claim_batch_id], lazy="select")
