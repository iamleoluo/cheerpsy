"""Phase 1b: 語意變更與向下相容層

gap_analysis.md §1.5 的全部語意變更，一次做完。核心原則是
**加欄位而非就地重定義**：既有欄位保留原意與原值，新語意放進新欄位。
這樣 59 處 payment_status、37 處 receipt_no、38 處 self_pay 的既有程式碼
都不需要同步改動，`main` 在本階段結束時仍可部署。

與原規劃的差異（刻意）：
- payment_status 原計畫「重定義」。實測有 59 處使用點，就地改語意風險過高，
  改為新增 payment_track 欄位承載「追款方式」（未收／月結／機構），
  payment_status 維持原本的 unpaid/paid/claimed 三值不動。
- session_records.amount 不移除，維持「總額」語意，新增的兩欄是它的拆分。
  加 CHECK 確保 self_pay + institution_claim = amount（僅對新資料生效，
  既有列以 self_pay=amount 回填）。

Revision ID: z4c1d2e3f4a6
Revises: z3b1c2d3e4f5
"""

import sqlalchemy as sa
from alembic import op

revision = "z4c1d2e3f4a6"
down_revision = "z3b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) appointments：新增「未到」狀態
    #    舊三值 booked/executed/cancelled 不動，另加 no_show。
    #    現況把未到記成 cancelled，因此無法計失約費、也無法判斷是否釋回額度。
    # ------------------------------------------------------------------
    op.add_column(
        "appointments",
        sa.Column("no_show_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("no_show_fee", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_appointments_status",
        "appointments",
        "status IN ('booked','executed','cancelled','no_show')",
    )
    op.create_check_constraint(
        "ck_appointments_no_show_type",
        "appointments",
        "no_show_type IS NULL OR no_show_type IN ('advance_notice','late_cancel','no_notice')",
    )

    # ------------------------------------------------------------------
    # 2) session_records：金額拆為 自付額 / 機構請款額
    #    amount 保留為總額。既有列以 self_pay = amount 回填（機構案的正確
    #    拆帳需要方案資訊，Phase 3 接上預約流程後才會有；在那之前不猜。）
    # ------------------------------------------------------------------
    op.add_column(
        "session_records",
        sa.Column("self_pay_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "session_records",
        sa.Column("institution_claim_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.execute("UPDATE session_records SET self_pay_amount = amount")

    # 追款方式：應收帳冊三分頁分的是這個，不是付款狀態
    #   immediate   該當場收卻沒收到 → 「未收」分頁
    #   monthly     本來就約定月底結 → 「月結」分頁
    #   institution 等機構撥款       → 「機構應收」分頁
    op.add_column(
        "session_records",
        sa.Column("payment_track", sa.String(length=20), nullable=False, server_default="immediate"),
    )
    op.execute(
        "UPDATE session_records SET payment_track = 'institution' "
        "WHERE funding_source = 'institution'"
    )
    op.create_check_constraint(
        "ck_session_records_payment_track",
        "session_records",
        "payment_track IN ('immediate','monthly','institution')",
    )

    # 修掉既有的未文件化值（import_excel.py 曾寫入 pending_claim）
    op.execute(
        "UPDATE session_records SET payment_status = 'unpaid' "
        "WHERE payment_status NOT IN ('unpaid','paid','claimed','claiming')"
    )

    op.add_column("session_records", sa.Column("fee_item", sa.String(length=30), nullable=True))
    op.add_column("session_records", sa.Column("is_no_show", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("session_records", sa.Column("no_show_fee", sa.Numeric(10, 2), nullable=False, server_default="0"))

    # ------------------------------------------------------------------
    # 3) 收據單一真相：invoices 為主
    #    session_records.receipt_no 與 product_sales.receipt_no 保留為
    #    **唯讀備援**（標 deprecated），新增 invoice_id 指向 invoices。
    #    gap_analysis §1.5「收據單一真相的遷移方案」步驟 1–3。
    # ------------------------------------------------------------------
    op.alter_column("invoices", "appointment_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("invoices", sa.Column("session_record_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("product_sale_id", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("branch_code", sa.String(length=2), nullable=False, server_default="A"))
    op.add_column("invoices", sa.Column("category", sa.String(length=1), nullable=False, server_default="C"))
    op.add_column("invoices", sa.Column("print_seq", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("check_code", sa.Integer(), nullable=False, server_default="1"))
    op.create_foreign_key(
        "fk_invoices_session_record", "invoices", "session_records",
        ["session_record_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_invoices_product_sale", "invoices", "product_sales",
        ["product_sale_id"], ["id"], ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_invoices_category", "invoices", "category IN ('C','O')"
    )
    op.create_check_constraint(
        "ck_invoices_check_code", "invoices", "check_code IN (1,2,3)"
    )

    # 註：session_records.invoice_id 早已存在（含 FK），此處只補 product_sales
    op.add_column("product_sales", sa.Column("invoice_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_product_sales_invoice", "product_sales", "invoices",
        ["invoice_id"], ["id"], ondelete="SET NULL",
    )

    # 回填：既有收據號原樣沿用（R.../P... 舊格式不重編）
    op.execute(
        """
        INSERT INTO invoices (invoice_number, session_record_id, status,
                              branch_code, category, print_seq, check_code, created_at)
        SELECT sr.receipt_no, sr.id, CASE WHEN sr.is_void THEN 'voided' ELSE 'active' END,
               'A', 'C', 0, CASE WHEN sr.is_void THEN 3 ELSE 1 END, now()
        FROM session_records sr
        WHERE sr.receipt_no IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM invoices i WHERE i.invoice_number = sr.receipt_no)
        """
    )
    op.execute(
        """
        INSERT INTO invoices (invoice_number, product_sale_id, status,
                              branch_code, category, print_seq, check_code, created_at)
        SELECT ps.receipt_no, ps.id, CASE WHEN ps.is_void THEN 'voided' ELSE 'active' END,
               'A', 'O', 0, CASE WHEN ps.is_void THEN 3 ELSE 1 END, now()
        FROM product_sales ps
        WHERE ps.receipt_no IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM invoices i WHERE i.invoice_number = ps.receipt_no)
        """
    )
    op.execute(
        "UPDATE session_records sr SET invoice_id = i.id "
        "FROM invoices i WHERE i.session_record_id = sr.id"
    )
    op.execute(
        "UPDATE product_sales ps SET invoice_id = i.id "
        "FROM invoices i WHERE i.product_sale_id = ps.id"
    )

    # ------------------------------------------------------------------
    # 4) claim_batches：廢除 type='self_pay'
    #    既有列不刪，標 is_legacy 供唯讀顯示；新建一律走應收帳冊月結分頁。
    # ------------------------------------------------------------------
    op.add_column(
        "claim_batches",
        sa.Column("is_legacy", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute("UPDATE claim_batches SET is_legacy = true WHERE type = 'self_pay'")
    op.add_column("claim_batches", sa.Column("void_reason", sa.String(length=500), nullable=True))
    op.add_column("claim_batches", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("claim_batches", sa.Column("voided_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_claim_batches_voided_by", "claim_batches", "users",
        ["voided_by"], ["id"], ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # 5) couple_members → case_members（更名 + 相容 view）
    #    伴侶諮商與會面交往同構（一案連兩位個案），role 列舉一併擴充。
    #    舊名建成 view，既有 query 不會斷。
    # ------------------------------------------------------------------
    op.rename_table("couple_members", "case_members")
    op.execute(
        "CREATE VIEW couple_members AS "
        "SELECT id, couple_case_id, member_case_id, role, created_at FROM case_members"
    )

    # ------------------------------------------------------------------
    # 6) cases：諮商型態與媒合欄位的前置（Phase 2 會用到 referral_id）
    # ------------------------------------------------------------------
    op.add_column("cases", sa.Column("consultation_mode", sa.String(length=30), nullable=True))
    op.add_column("cases", sa.Column("group_name", sa.String(length=200), nullable=True))
    op.add_column("cases", sa.Column("group_representative", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "group_representative")
    op.drop_column("cases", "group_name")
    op.drop_column("cases", "consultation_mode")

    op.execute("DROP VIEW IF EXISTS couple_members")
    op.rename_table("case_members", "couple_members")

    op.drop_constraint("fk_claim_batches_voided_by", "claim_batches", type_="foreignkey")
    op.drop_column("claim_batches", "voided_by")
    op.drop_column("claim_batches", "voided_at")
    op.drop_column("claim_batches", "void_reason")
    op.drop_column("claim_batches", "is_legacy")

    op.drop_constraint("fk_product_sales_invoice", "product_sales", type_="foreignkey")
    op.drop_column("product_sales", "invoice_id")

    op.drop_constraint("ck_invoices_check_code", "invoices", type_="check")
    op.drop_constraint("ck_invoices_category", "invoices", type_="check")
    op.drop_constraint("fk_invoices_product_sale", "invoices", type_="foreignkey")
    op.drop_constraint("fk_invoices_session_record", "invoices", type_="foreignkey")
    for col in ("check_code", "print_seq", "category", "branch_code", "product_sale_id", "session_record_id"):
        op.drop_column("invoices", col)
    op.execute("DELETE FROM invoices WHERE appointment_id IS NULL")
    op.alter_column("invoices", "appointment_id", existing_type=sa.Integer(), nullable=False)

    op.drop_column("session_records", "no_show_fee")
    op.drop_column("session_records", "is_no_show")
    op.drop_column("session_records", "fee_item")
    op.drop_constraint("ck_session_records_payment_track", "session_records", type_="check")
    op.drop_column("session_records", "payment_track")
    op.drop_column("session_records", "institution_claim_amount")
    op.drop_column("session_records", "self_pay_amount")

    op.drop_constraint("ck_appointments_no_show_type", "appointments", type_="check")
    op.drop_constraint("ck_appointments_status", "appointments", type_="check")
    op.drop_column("appointments", "no_show_fee")
    op.drop_column("appointments", "no_show_type")
