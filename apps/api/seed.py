"""Seed script: creates initial users (1 admin, 1 accountant, 17 therapists) and rooms."""

import sys

from app.auth.password import hash_password
from app.database import Base, engine, SessionLocal
from app.models import *  # noqa: F401,F403

# P0（V2升級計畫 02 §1.1、06 P0）：定稿確定的 12 間診間主檔，取代下面
# seed() 裡 floor_config 那份 13 間的測試資料。2C/2E 為兒童遊戲室，
# 其餘晤談室；2D/3D/3F 標記大間（原型 JS 排序邏輯用得到，見 02 §5.1
# available-rooms 端點）。1F 只有 1A 一間。
FINAL_ROOM_ROSTER = [
    ("1A", 1, "general", "normal"),
    ("2A", 2, "general", "normal"),
    ("2B", 2, "general", "normal"),
    ("2C", 2, "play", "normal"),
    ("2D", 2, "general", "large"),
    ("2E", 2, "play", "normal"),
    ("3A", 3, "general", "normal"),
    ("3B", 3, "general", "normal"),
    ("3C", 3, "general", "normal"),
    ("3D", 3, "general", "large"),
    ("3E", 3, "general", "normal"),
    ("3F", 3, "general", "large"),
]


def rebuild_room_roster(force: bool = False):
    """把診間主檔重建為定稿的 12 間。

    這是「資料」層面的決定，不是 schema migration（欄位已由
    aa1a2b3c4d5f1 這支 migration 加好）。刻意獨立於 seed() 之外呼叫，
    因為這個動作在正式環境是不可逆的業務決定（見 06 P0 表格備註）：
    既有 13 間測試診間會被清空重建，任何引用舊 room_id 的預約會被
    一併清掉（診療所已確認現有資料為測試資料，可以這樣做，見對話記錄）。

    如果 rooms 底下已經有真實資料（appointments 引用了現有 room_id），
    預設會拒絕執行、要求加 --force 才會連同那些預約一起清掉，避免
    在正式環境誤觸。
    """
    db = SessionLocal()
    existing_rooms = db.query(Room).all()
    if existing_rooms:
        referenced = db.query(Appointment).filter(Appointment.room_id.isnot(None)).count()
        if referenced and not force:
            print(
                f"拒絕執行：現有 {len(existing_rooms)} 間診間中有 {referenced} 筆預約引用它們。"
                f"\n若確認這些是測試資料、可以一併清空，請加 --force 參數重跑："
                f"\n    python seed.py --rebuild-rooms --force"
            )
            db.close()
            return
        db.query(Appointment).filter(Appointment.room_id.isnot(None)).delete(synchronize_session=False)
        for r in existing_rooms:
            db.delete(r)
        db.commit()
        print(f"已清空 {len(existing_rooms)} 間舊診間" + ("（含引用它們的測試預約）" if referenced else ""))

    for code, floor, use_type, size in FINAL_ROOM_ROSTER:
        db.add(Room(name=code, floor=floor, room_code=code, use_type=use_type, size=size))
    db.commit()
    db.close()
    print(f"已建立定稿版 {len(FINAL_ROOM_ROSTER)} 間診間：{', '.join(c for c, *_ in FINAL_ROOM_ROSTER)}")


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(User).first():
        print("Database already seeded, skipping.")
        db.close()
        return

    default_pw = hash_password("admin123")

    users = [
        User(email="admin@cheerpsy.com", password_hash=default_pw, name="管理員", role="admin"),
        User(email="accountant@cheerpsy.com", password_hash=default_pw, name="會計", role="accountant"),
    ]

    therapist_names = [
        "呂孟育", "林紀宇", "林容蒂", "邱似齡", "蔡孟潔",
        "陳慧苓", "游子瑩", "葉邦彥", "鄭幼毅", "楊顯欽",
        "劉柏宏", "邱惟雅", "潘柔靜", "邱意祺", "劉彥君",
        "羅紀萱", "黃慧婷",
    ]

    for i, name in enumerate(therapist_names, start=1):
        code = f"T{i:03d}"
        users.append(
            User(
                email=f"therapist{i}@cheerpsy.com",
                password_hash=default_pw,
                name=name,
                role="therapist",
                user_code=code,
            )
        )

    db.add_all(users)

    # P0：全新環境直接用定稿版 12 間診間，不再產生舊的 13 間測試資料。
    # 既有環境（已經有 13 間舊資料的）不會走到這裡（上面 db.query(User).first()
    # 已經 skip），要換成新名冊得另外跑 rebuild_room_roster()。
    rooms = [
        Room(name=code, floor=floor, room_code=code, use_type=use_type, size=size)
        for code, floor, use_type, size in FINAL_ROOM_ROSTER
    ]

    db.add_all(rooms)
    db.commit()
    db.close()
    print(f"Seeded {len(users)} users and {len(rooms)} rooms.")


if __name__ == "__main__":
    if "--rebuild-rooms" in sys.argv:
        rebuild_room_roster(force="--force" in sys.argv)
    else:
        seed()
