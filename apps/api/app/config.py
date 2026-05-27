from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://cheerpsy:cheerpsy@localhost:5432/cheerpsy"
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    ID_ENCRYPTION_KEY: str = "dev-encryption-key-change-in-production"
    CORS_ORIGINS: str = "http://localhost:3000"

    # 外出諮商（session_type="outdoor"）心理師抽成保底金額
    # 公式：bonus = max(0, min(amount, OUTPATIENT_MIN_FEE) - amount * rate)
    # 診所讓利上限為「補心理師抽成至此金額」，但總收入不夠時就全額給心理師、診所領 0（不墊錢）
    OUTPATIENT_MIN_FEE: int = 1000

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
