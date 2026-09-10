from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import appointments, audit, auth, case_quotas, cases, churn, claim_batches, dashboard, data_import, export, fee_items, health, institutions, invoices, ledger, notifications, payouts, petty_cash, product_sales, receipts, reminders, reports, rooms, room_calendar
from app.routers import quota_templates, venues
# 機構合約子系統：管理頁 API（合約/方案/費率/個案機構狀態/核銷案容器）。
# 見 V2升級計畫 07_機構合約子系統架構.html。這是唯一允許主系統 import
# app.institution.* 的地方之一（另一處是下面 register()），且僅止於
# 「掛載路由」與「註冊 provider」，不參與任何業務邏輯。
from app.institution.routers import admin as institution_admin
from app.institution.adapter import InstitutionFundingProvider
from app.funding import registry as funding_registry
# 媒合管理子系統：小的獨立子系統，媒合出第一次（初診）預約後即交棒給
# 上面既有的個案／預約系統（app.routers.cases / app.routers.appointments）。
from app.referral.routers import admin as referral_admin

app = FastAPI(title="CheerPsy API", version="2.0.0")

# 啟動時把機構合約子系統接上。若診所哪天不需要機構方案（純自費），
# 拿掉這一行即可——主系統其餘程式碼會自動降級為 NullProvider 行為。
funding_registry.register(InstitutionFundingProvider())

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(cases.router)
app.include_router(appointments.router)
app.include_router(rooms.router)
app.include_router(room_calendar.router)
app.include_router(fee_items.router)
app.include_router(ledger.router)
app.include_router(invoices.router)
app.include_router(petty_cash.router)
app.include_router(institutions.router)
app.include_router(reports.router)
app.include_router(reminders.router)
app.include_router(churn.router)
app.include_router(payouts.router)
app.include_router(audit.router)
app.include_router(export.router)
app.include_router(data_import.router)
app.include_router(claim_batches.router)
app.include_router(notifications.router)
app.include_router(product_sales.router)
app.include_router(receipts.router)
app.include_router(case_quotas.router)
app.include_router(quota_templates.router)
app.include_router(venues.router)
app.include_router(institution_admin.router)
app.include_router(referral_admin.router)
