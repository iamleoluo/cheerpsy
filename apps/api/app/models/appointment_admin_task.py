"""行政流程提醒（02 §1.2、07 §5.3 ⑥、v7 診間日曆定案）。

機構方案在 inst_plans.admin_checklist / therapist_checklist 存了一份「這個
方案每次要辦哪些行政事項」的清單（JSON 字串陣列），報價時也會跟著 Quote
帶出來。缺的是把它**落成每一筆預約上可勾選的項目**——這樣才有辦法記
「誰在什麼時候辦好了哪一項」，也才有辦法判斷「這格還有沒有未完成事項」。

這件事是承重的：診間日曆的方塊要「整格轉灰」有三個條件，其中一個就是
行政事項全部勾完。沒有這張表，那個條件永遠無法成立。

side 分兩邊：admin 的項目櫃台勾、therapist 的項目心理師勾，各自只看到
自己那半（權限在 router 層擋）。
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class AppointmentAdminTask(Base):
    __tablename__ = "appointment_admin_tasks"

    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    title = Column(String(200), nullable=False)
    side = Column(String(20), nullable=False, default="admin", server_default="admin")  # admin | therapist
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    is_done = Column(Boolean, nullable=False, default=False, server_default="false")
    done_at = Column(DateTime(timezone=True), nullable=True)
    done_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # 共用帳號（實習心理師）登入時自填的姓名快照，顯示成「✓ 林怡君 08/19 09:12」
    done_by_name = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    appointment = relationship("Appointment", back_populates="admin_tasks")
    done_user = relationship("User", foreign_keys=[done_by])
