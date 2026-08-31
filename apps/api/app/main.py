from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import appointments, audit, auth, case_quotas, cases, churn, claim_batches, dashboard, data_import, export, health, institutions, invoices, ledger, notifications, payouts, petty_cash, product_sales, receipts, reminders, reports, rooms
from app.routers import quota_templates
from app.routers import institution_contracts, institution_plans

app = FastAPI(title="CheerPsy API", version="2.0.0")

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
app.include_router(institution_contracts.router)
app.include_router(institution_plans.router)
