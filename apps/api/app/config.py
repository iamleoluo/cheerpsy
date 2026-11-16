from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy"
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    ID_ENCRYPTION_KEY: str = "dev-encryption-key-change-in-production"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Google 日曆同步（docs/gcal-sync-plan.md）。全部留空時 API 照常啟動，
    # 只有「連結 Google」會回 503 並說明缺哪個設定，不會靜默失敗。
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    # 必須與 Google Cloud 的 Authorized redirect URI 完全一致，例如 http://localhost:8000/settings/google/callback
    GOOGLE_OAUTH_REDIRECT_URI: str = ""
    # 加密 refresh token 用的 Fernet 金鑰。遺失就無法解密、必須重新授權，所以要備份在診所的密碼管理工具，不進 git。
    # 產生：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    GCAL_TOKEN_FERNET_KEY: str = ""
    # 授權完成後把管理員導回的前端網址；留空就用 CORS_ORIGINS 的第一個
    FRONTEND_URL: str = ""

    # 外出諮商（session_type="outdoor"）心理師抽成保底金額
    # 公式：bonus = max(0, min(amount, OUTPATIENT_MIN_FEE) - amount * rate)
    # 診所讓利上限為「補心理師抽成至此金額」，但總收入不夠時就全額給心理師、診所領 0（不墊錢）
    OUTPATIENT_MIN_FEE: int = 1000

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
