from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """存活檢查。刻意實際查一次 DB，而不是單純回 200 ——
    否則即使 DATABASE_URL 設錯、連線池耗盡等問題，這支 endpoint 仍會回「ok」，
    形同虛設。"""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
        db_error = None
    except Exception as e:
        db_ok = False
        db_error = str(e)

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "database_error": db_error,
    }
