from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import appointments, audit, auth, cases, churn, dashboard, export, health, institutions, invoices, ledger, payouts, petty_cash, reminders, reports, rooms

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
