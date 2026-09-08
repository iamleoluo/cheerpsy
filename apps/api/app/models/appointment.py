from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE
from sqlalchemy.orm import relationship

from app.database import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    appointment_number = Column(String(50), unique=True, nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    session_type = Column(String(20), nullable=False)  # in_person, online, outdoor（型式）
    # 諮商型態（07 §6.2 的計價維度，與 session_type 不同軸）：individual / couple /
    # family / parenting / group / lecture / meeting。機構方案的費率規則會用它比對
    # ——家防中心的 個別$2000 / 親職$1000 / 家族$2400 三種價都是「現場」。
    consult_type = Column(String(20), nullable=False, default="individual", server_default="individual")
    # 服務地點（07 §6.2）：clinic 所內 / home 到宅 / onsite 入廠 / offsite 其他外展
    location_kind = Column(String(20), nullable=False, default="clinic", server_default="clinic")
    time_range = Column(TSTZRANGE, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default="booked")  # booked, executed, cancelled
    funding_source = Column(String(20), nullable=False, default="self_pay", server_default="self_pay")  # self_pay | institution
    # quota_id：舊路徑（case_institution_quotas），既有的建立/取消預約流程仍在用，
    # 暫時保留、尚未移除。新路徑是下面 plan_id + plan_quote，見 07 §4.2、§7.1。
    # TODO(P2b)：appointments 路由改接 funding_registry 後，quota_id 可以廢止，
    # case_institution_quotas / quota_templates 兩張表資料遷移進 inst_enrollments。
    quota_id = Column(Integer, ForeignKey("case_institution_quotas.id"), nullable=True)
    visit_seq = Column(Integer, nullable=True)
    batch_id = Column(String(50), nullable=True, index=True)
    # 合療標記：有值 = 這是某伴侶案的合療場次（case_id 仍為付款方）
    couple_case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ── 機構合約子系統的報價快照（07 §4.2、§7.1，已於 P2b 接上）─────────────
    # 這 6 個欄位是主系統為了接上子系統唯一新增的東西。routers/appointments.py
    # 的 create_appointment()：POST /appointments 帶 plan_id 時呼叫
    # funding_registry.get_provider().quote() 拿到 Quote，整包塞進 plan_quote，
    # 其餘 5 個攤平欄位從 Quote 取出寫入，同一交易內呼叫 .reserve()。
    plan_id = Column(Integer, ForeignKey("inst_plans.id"), nullable=True)
    case_payable = Column(Numeric(10, 2), nullable=True)
    institution_payable = Column(Numeric(10, 2), nullable=True)
    compensation_mode = Column(String(12), nullable=True)  # commission | kickback | none
    commissionable_base = Column(Numeric(10, 2), nullable=True)
    plan_quote = Column(JSONB, nullable=True)  # 完整 Quote 快照（見 funding/dto.py Quote）

    # ── 出席狀態機（P1，07 升級計畫 01 §A1、02 §4.1）──────────────────────
    # 這是整個 V2 改造最核心的一組欄位：場次是否成立，從「時間到就自動」
    # 改成「使用者按出來的」。check_in_status 三態：
    #   pending（待報到，建立預約時的初始值）
    #   arrived（已到——appointments/{id}/check-in 端點寫入，此刻才建立
    #            session_record；services/settlement.py 的 materialize_due_
    #            appointments() 降級為補登安全網，只處理仍是 pending 的漏網之魚）
    #   no_show（未到——不建立 session_record，appt.status 仍是 'booked'
    #            不轉 cancelled，供對帳追蹤；機構額度由 reserved 還原，
    #            不是釋回，見 01 §C3）
    check_in_status = Column(String(20), nullable=False, default="pending", server_default="pending")
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    no_show_reason = Column(String(20), nullable=True)  # case_leave | last_minute_cancel | unreachable | other
    no_show_note = Column(String(200), nullable=True)
    no_show_followup = Column(String(20), nullable=True)  # 催繳方式，具體選項待丙5確認（01 §F 丙5）

    # ── 加時 / 調整實際執行時數（01 §C1、04 §2.4）──────────────────────
    # 收款前按「調整實際時數」會寫這兩欄，並依單價重算 amount、同步回寫
    # time_range。C1 裁示：回寫若撞到相鄰預約就擋下，畫面提示請洽行政——
    # 不自動幫忙擠掉下一位。保留原始起訖在這裡，是為了讓「原訂 vs 實際」
    # 的差異在日報表與稽核上看得出來。
    actual_start = Column(DateTime(timezone=True), nullable=True)
    actual_end = Column(DateTime(timezone=True), nullable=True)
    duration_adjusted_at = Column(DateTime(timezone=True), nullable=True)
    duration_adjusted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    duration_note = Column(String(200), nullable=True)

    # ── 視訊連結（06 P4）────────────────────────────────────────────────
    # 心理師自行貼上，系統不自動產生（定稿明確排除自動產生）。貼上後行政端
    # 會出現「請通知行政轉發給個案」待辦，轉發完按一下記時間。
    video_link = Column(String(500), nullable=True)
    video_forwarded_at = Column(DateTime(timezone=True), nullable=True)
    video_forwarded_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ── 個案請假（心理師端「為此次預約請假」，原因選填）──────────────────
    # 與「未到」不同：請假是事前知道的，時段要釋出、不產生應收、也不收
    # 機構未到補助（補助補的是個案沒出現，不是這場沒發生）。
    leave_reason = Column(String(200), nullable=True)
    leave_at = Column(DateTime(timezone=True), nullable=True)
    leave_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    case = relationship("Case", back_populates="appointments", foreign_keys=[case_id])
    couple_case = relationship("Case", foreign_keys=[couple_case_id])
    therapist = relationship("User", back_populates="appointments", foreign_keys=[therapist_id])
    room = relationship("Room")
    session_record = relationship("SessionRecord", back_populates="appointment", uselist=False)
    invoice = relationship("Invoice", back_populates="appointment", uselist=False)
    reminders = relationship("ReminderLog", back_populates="appointment")
    admin_tasks = relationship(
        "AppointmentAdminTask", back_populates="appointment",
        order_by="AppointmentAdminTask.sort_order", cascade="all, delete-orphan",
    )
