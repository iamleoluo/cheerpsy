"""房間衝突 DB 層防護：EXCLUDE USING GIST

見 V2升級計畫 01 §C5（已裁示：需要）、02 §2、08 §8 下一步第1項。

現況缺口：routers/appointments.py 的 _check_room_conflict() 是應用層
SELECT-then-INSERT，兩個併發請求可以同時通過檢查、都插入成功，造成同一
診間同一時段被排進兩筆預約。你的原稿也明寫「同一診間同時段不可重複預約，
由資料庫層強制（非僅前端檢查）」，但程式碼裡從來沒有這個約束。

這支 migration 補上：PostgreSQL 的 EXCLUDE USING GIST 約束，只排除
status != 'cancelled' 且 room_id 不為 NULL 的重疊區段——與應用層檢查的
條件完全一致（見 _check_room_conflict 的 SQL）。

需要 btree_gist extension，因為 room_id 是純量整數，不是原生支援 GIST
的型別（time_range 這個 TSTZRANGE 本身就支援），要靠 btree_gist 讓
"room_id WITH =" 這種等值比較也能參與 GIST 索引。

執行前提：若既有資料已經有重疊（理論上不該發生，因為應用層檢查一直都在
擋，但保險起見用 DO block 檢查一次，若有衝突直接讓 migration failed-fast，
而不是靜默建出一個實際上擋不住任何東西的壞約束）。

Revision ID: aa5a2b3c4d5f5
Revises: aa4a2b3c4d5f4
Create Date: 2026-09-07 00:00:00.000004
"""
from alembic import op

revision = "aa5a2b3c4d5f5"
down_revision = "aa4a2b3c4d5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # Fail-fast 檢查：若既有資料已經有重疊，直接讓 migration 失敗並印出衝突的
    # appointment id，而不是靜默建出一個實際上永遠會失敗的約束（那樣正式環境
    # upgrade 時才會炸，而且訊息不會告訴你是哪幾筆資料的問題）。
    op.execute(
        """
        DO $$
        DECLARE
            conflict_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO conflict_count
            FROM appointments a1
            JOIN appointments a2 ON a1.room_id = a2.room_id
                AND a1.id < a2.id
                AND a1.time_range && a2.time_range
            WHERE a1.status != 'cancelled' AND a2.status != 'cancelled'
                AND a1.room_id IS NOT NULL;
            IF conflict_count > 0 THEN
                RAISE EXCEPTION
                    '% 筆既有預約在同一診間同一時段重疊，無法建立 EXCLUDE 約束。'
                    '請先用以下查詢找出並人工處理這些紀錄，再重跑本 migration：'
                    'SELECT a1.id, a2.id, a1.room_id FROM appointments a1 JOIN appointments a2 '
                    'ON a1.room_id=a2.room_id AND a1.id<a2.id AND a1.time_range && a2.time_range '
                    'WHERE a1.status!=''cancelled'' AND a2.status!=''cancelled''',
                    conflict_count;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT excl_room_time_overlap
        EXCLUDE USING GIST (room_id WITH =, time_range WITH &&)
        WHERE (status != 'cancelled' AND room_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS excl_room_time_overlap")
    # 不移除 btree_gist extension：其他表／未來 migration 可能也在用，
    # 移除 extension 是全域性的破壞性操作，交給 DBA 手動決定。
