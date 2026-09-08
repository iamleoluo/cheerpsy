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

    # 收據編號格式。01 §C4 / 09 §7 把這條列為「唯一還沒定案」的規則，所以做成可切換：
    #   v7     A{YYYYMMDD}{C|O}{流水3碼}-{1開立/2重印/3作廢}   例 A20260801C021-1（診療所看過的原型格式）
    #   legacy R{YYYYMMDD}{流水4碼}                            例 R202608010021（舊程式碼格式）
    # 見 app/services/numbering.py。
    RECEIPT_NUMBER_FORMAT: str = "v7"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
