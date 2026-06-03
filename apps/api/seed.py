"""Seed script: creates initial users (1 admin, 1 accountant, 17 therapists) and rooms."""

from app.auth.password import hash_password
from app.database import Base, engine, SessionLocal
from app.models import *  # noqa: F401,F403


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
        "劉子瑩", "楊子賢", "林郁珊", "蕭雅文",
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

    rooms = []
    floor_config = [
        (1, ["1A 談話室", "1B 談話室", "1C 遊戲治療室", "1D 團體室"]),
        (2, ["2A 談話室", "2B 談話室", "2C 談話室", "2D 藝術治療室"]),
        (3, ["3A 談話室", "3B 談話室", "3C 談話室", "3D 沙遊治療室", "3E 談話室"]),
    ]
    for floor, room_names in floor_config:
        for rname in room_names:
            code = rname.split(" ")[0]
            has_special = any(k in rname for k in ["遊戲", "藝術", "沙遊", "團體"])
            rooms.append(Room(name=rname, floor=floor, room_code=code, has_special_equipment=has_special))

    db.add_all(rooms)
    db.commit()
    db.close()
    print(f"Seeded {len(users)} users and {len(rooms)} rooms.")


if __name__ == "__main__":
    seed()
