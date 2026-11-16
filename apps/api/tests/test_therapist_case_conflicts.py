"""心理師／個案時段衝突：同一心理師、同一個案（含伴侶案成員）在 booked／executed 預約重疊 → 409。
訊息只寫時段，不寫個案或心理師姓名。建立、批次、改期、媒合預約初診都要擋；改期排除自己。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.couple_member import CoupleMember
from app.models.room import Room
from app.services import slot_check

A_NAME, B_NAME = "王甲個案", "李乙個案"


def _t(days=3, hour=10, minutes=60):
    s = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return s, s + timedelta(minutes=minutes)


@pytest.fixture()
def world(make_user, make_case, room, db):
    t1, t2 = make_user("therapist", name="林一心理師"), make_user("therapist", name="陳二心理師")
    staff = make_user("staff")
    a, a2 = make_case(t1, A_NAME), make_case(t1, "趙丙個案")
    b = make_case(t2, B_NAME)
    couple = make_case(t1, "甲乙伴侶案", case_type="couple")
    db.add_all([CoupleMember(couple_case_id=couple.id, member_case_id=a.id),
                CoupleMember(couple_case_id=couple.id, member_case_id=b.id)])
    room2 = Room(name="晤談室 3C", floor=3, room_code="3C")
    db.add(room2)
    db.commit()
    return dict(t1=t1, t2=t2, staff=staff, a=a, a2=a2, b=b, couple=couple, room=room, room2=room2)


def book(client, auth, who, case, room, s, e, **extra):
    return client.post("/appointments", headers=auth(who), json={
        "case_id": case.id, "room_id": room.id, "session_type": "in_person", "amount": 1000,
        "start_time": s.isoformat(), "end_time": e.isoformat(), **extra})


def no_names(r):
    for n in (A_NAME, B_NAME, "趙丙個案", "甲乙伴侶案", "林一心理師", "陳二心理師"):
        assert n not in r.text


def test_same_therapist_overlap_is_409_even_in_another_room(client, auth, world):
    w = world
    s, e = _t()
    assert book(client, auth, w["staff"], w["a"], w["room"], s, e).status_code == 201
    r = book(client, auth, w["staff"], w["a2"], w["room2"], s + timedelta(minutes=30), e + timedelta(minutes=30))
    assert r.status_code == 409 and "心理師" in r.json()["detail"] and "已有其他預約" in r.json()["detail"]
    no_names(r)
    # 首尾相接不算重疊；不同心理師同時段沒問題
    assert book(client, auth, w["staff"], w["a2"], w["room2"], e, e + timedelta(hours=1)).status_code == 201
    assert book(client, auth, w["staff"], w["b"], w["room2"], s, e).status_code == 201


def test_cancelled_and_no_show_release_the_slot(client, auth, world):
    w = world
    s, e = _t()
    first = book(client, auth, w["staff"], w["a"], w["room"], s, e).json()["id"]
    assert client.put(f"/appointments/{first}/cancel", headers=auth(w["staff"])).status_code == 200
    assert book(client, auth, w["staff"], w["a2"], w["room2"], s, e).status_code == 201


def test_case_overlap_is_409(client, auth, world, db, monkeypatch):
    w = world
    s, e = _t()
    assert book(client, auth, w["staff"], w["a"], w["room"], s, e).status_code == 201
    # 直接驗證個案檢查本身（心理師檢查會先擋同一位心理師，所以另外單獨呼叫）
    with pytest.raises(Exception) as ei:
        slot_check.assert_case_free(db, [w["a"].id], s, e)
    assert ei.value.status_code == 409 and A_NAME not in ei.value.detail
    slot_check.assert_case_free(db, [w["a2"].id], s, e)  # 別的個案不受影響
    slot_check.assert_case_free(db, [w["a"].id], e, e + timedelta(hours=1))  # 首尾相接


def test_couple_members_conflict_with_each_other_and_with_the_couple_case(client, auth, world):
    w = world
    s, e = _t()
    # 乙（心理師 2）的個別預約
    assert book(client, auth, w["staff"], w["b"], w["room"], s, e).status_code == 201
    # 伴侶案合療（心理師 1，付款方甲）同時段：乙是伴侶案成員 → 個案衝突
    r = book(client, auth, w["staff"], w["a"], w["room2"], s, e, couple_case_id=w["couple"].id)
    assert r.status_code == 409 and "個案" in r.json()["detail"]
    no_names(r)
    # 換個時段可以；之後甲的個別預約若與合療重疊，也被擋（甲是成員）
    s2, e2 = _t(hour=14)
    assert book(client, auth, w["staff"], w["a"], w["room2"], s2, e2, couple_case_id=w["couple"].id).status_code == 201
    r2 = book(client, auth, w["staff"], w["b"], w["room"], s2, e2)  # 乙是成員，合療佔用了乙
    assert r2.status_code == 409 and "個案" in r2.json()["detail"]


def test_reschedule_excludes_itself_but_not_others(client, auth, world):
    w = world
    s, e = _t()
    mine = book(client, auth, w["staff"], w["a"], w["room"], s, e).json()["id"]
    other = book(client, auth, w["staff"], w["a2"], w["room2"], e, e + timedelta(hours=1)).json()["id"]
    # 往後挪 30 分：與自己原本的時段重疊，不算衝突；但會撞到另一筆 → 409
    r = client.put(f"/appointments/{mine}", headers=auth(w["staff"]), json={
        "start_time": (s + timedelta(minutes=30)).isoformat(), "end_time": (e + timedelta(minutes=30)).isoformat()})
    assert r.status_code == 409 and "心理師" in r.json()["detail"]
    ok = client.put(f"/appointments/{mine}", headers=auth(w["staff"]), json={
        "start_time": (s - timedelta(minutes=30)).isoformat(), "end_time": (e - timedelta(minutes=30)).isoformat()})
    assert ok.status_code == 200, ok.text
    # 只換診間（時間沒動）不受影響
    assert client.put(f"/appointments/{other}", headers=auth(w["staff"]), json={"room_id": w["room"].id}).status_code == 200


def test_batch_rejects_overlapping_slots(client, auth, world):
    w = world
    s, e = _t()
    s2, e2 = _t(days=4)
    r = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["a"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s.isoformat(), "end_time": e.isoformat()},
                  {"start_time": (s + timedelta(minutes=30)).isoformat(), "end_time": (e + timedelta(minutes=30)).isoformat()},
                  {"start_time": s2.isoformat(), "end_time": e2.isoformat()}]})
    assert r.status_code == 409  # 同診間先被診間檢查擋下；換診間時由心理師檢查擋下
    # 全部不成立（交易整批回復）
    assert client.get("/appointments", headers=auth(w["staff"])).json() == []
    ok = client.post("/appointments/batch", headers=auth(w["staff"]), json={
        "case_id": w["a"].id, "room_id": w["room"].id, "session_type": "in_person", "amount": 1000,
        "slots": [{"start_time": s.isoformat(), "end_time": e.isoformat()},
                  {"start_time": s2.isoformat(), "end_time": e2.isoformat()}]})
    assert ok.status_code == 201 and len(ok.json()) == 2


def test_referral_convert_checks_the_therapist(client, auth, world, db):
    from app.models.referral import (ReferralDispatch, ReferralDispatchTarget, ReferralRequest, ReferralSlotOffer)

    w = world
    r = ReferralRequest(dispatch_code="261117001", name="新個案", consultation_mode="individual", status="converted")
    db.add(r)
    db.flush()
    d = ReferralDispatch(referral_id=r.id, seq=1)
    db.add(d)
    db.flush()
    t = ReferralDispatchTarget(dispatch_id=d.id, therapist_id=w["t1"].id, status="accepted")
    db.add(t)
    db.flush()
    s, e = _t()
    day = s.astimezone(slot_check.TZ).date()
    slot = ReferralSlotOffer(target_id=t.id, seq=1, slot_date=day, start_time="10:00", end_time="11:00")
    db.add(slot)
    db.commit()
    start = datetime.fromisoformat(f"{day}T10:00:00+08:00")
    assert book(client, auth, w["staff"], w["a"], w["room"], start, start + timedelta(hours=1)).status_code == 201
    r1 = client.post(f"/referrals/{r.id}/convert", headers=auth(w["staff"]),
                     json={"slot_id": slot.id, "session_type": "online", "amount": 1200})
    assert r1.status_code == 409 and "心理師" in r1.json()["detail"]
    no_names(r1)
