"""sweep_expired：搬到 services 後行為不變；背景程序定時呼叫；重複執行冪等。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.referral import ReferralDispatch, ReferralDispatchTarget, ReferralRequest
from app.services import referral_sweep


@pytest.fixture()
def pending(db, make_user):
    t = make_user("therapist")
    r = ReferralRequest(dispatch_code="261117200", name="新個案", consultation_mode="individual", status="matching")
    db.add(r)
    db.flush()
    d = ReferralDispatch(referral_id=r.id, seq=1, dispatched_at=datetime.now(timezone.utc) - timedelta(hours=30))
    db.add(d)
    db.flush()
    tg = ReferralDispatchTarget(dispatch_id=d.id, therapist_id=t.id, status="pending")
    db.add(tg)
    db.commit()
    return r, d, tg


def test_remind_after_one_day_only_once(db, pending):
    r, d, tg = pending
    assert referral_sweep.sweep_expired(db) == 1
    db.refresh(tg)
    first = tg.reminded_at
    assert tg.status == "pending" and first is not None
    # 再跑不會重複提醒、時間不變
    assert referral_sweep.sweep_expired(db) == 0
    db.refresh(tg)
    assert tg.reminded_at == first


def test_expire_after_three_days_and_referral_fails_once(db, pending):
    r, d, tg = pending
    d.dispatched_at = datetime.now(timezone.utc) - timedelta(days=4)
    db.commit()
    assert referral_sweep.sweep_expired(db) == 1
    db.refresh(tg), db.refresh(d), db.refresh(r)
    assert tg.status == "expired" and d.status == "expired" and r.status == "failed"
    resolved = d.resolved_at
    # 冪等：不再變動，退回時間不會被改寫
    assert referral_sweep.sweep_expired(db) == 0
    db.refresh(d), db.refresh(r)
    assert d.resolved_at == resolved and r.status == "failed"


def test_fresh_dispatch_untouched(db, pending):
    r, d, tg = pending
    d.dispatched_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.commit()
    assert referral_sweep.sweep_expired(db) == 0


def test_router_still_exposes_sweep_and_list_page_triggers_it(client, auth, db, make_user, pending):
    from app.routers import referrals

    assert referrals.sweep_expired is referral_sweep.sweep_expired
    r, d, tg = pending
    d.dispatched_at = datetime.now(timezone.utc) - timedelta(days=4)
    db.commit()
    assert client.get("/referrals", headers=auth(make_user("staff"))).status_code == 200
    db.refresh(tg)
    assert tg.status == "expired"


def test_run_sweep_commits_with_own_session_and_is_idempotent(db, pending):
    r, d, tg = pending
    d.dispatched_at = datetime.now(timezone.utc) - timedelta(days=4)
    db.commit()
    assert referral_sweep.run_sweep() == 1
    assert referral_sweep.run_sweep() == 0
    db.refresh(tg)
    assert tg.status == "expired"


def test_run_sweep_never_raises(caplog):
    def boom():
        raise RuntimeError("db down")

    class BadSession:
        def query(self, *a, **k):
            raise RuntimeError("query failed")

        def rollback(self):
            pass

        def close(self):
            pass

    assert referral_sweep.run_sweep(session_factory=lambda: BadSession()) == 0
    assert referral_sweep.run_sweep(session_factory=boom) == 0  # 連開 session 都失敗也只記 log


def test_worker_runs_sweep_hourly_not_every_loop():
    from app import gcal_worker

    assert gcal_worker.sweep_due(None, 100.0)  # 啟動後第一輪就跑
    assert not gcal_worker.sweep_due(100.0, 100.0 + 3599)
    assert gcal_worker.sweep_due(100.0, 100.0 + 3600)


def test_worker_loop_survives_a_failing_sweep(monkeypatch):
    from app import gcal_worker

    calls = {"sweep": 0, "push": 0}

    def bad_sweep():
        calls["sweep"] += 1
        raise RuntimeError("boom")

    def push():
        calls["push"] += 1
        if calls["push"] >= 3:
            gcal_worker._stop.set()
        return 0

    monkeypatch.setattr(gcal_worker.referral_sweep, "run_sweep", bad_sweep)
    monkeypatch.setattr(gcal_worker.gcal_push, "run_once", push)
    monkeypatch.setattr(gcal_worker, "IDLE_SECONDS", 0)
    gcal_worker._stop.clear()
    try:
        gcal_worker.main()
    finally:
        gcal_worker._stop.clear()
    assert calls["sweep"] == 1 and calls["push"] == 3  # 一小時內只跑一次；掃描失敗不影響 outbox 迴圈
