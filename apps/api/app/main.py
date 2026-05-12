from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import appointments, auth, cases, health, invoices, ledger, petty_cash, reports, rooms

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
app.include_router(cases.router)
app.include_router(appointments.router)
app.include_router(rooms.router)
app.include_router(ledger.router)
app.include_router(invoices.router)
app.include_router(petty_cash.router)
app.include_router(reports.router)
