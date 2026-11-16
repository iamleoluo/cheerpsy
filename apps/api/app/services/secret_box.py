"""機密加密（Fernet）：Google refresh token 入庫前加密、只在呼叫 Google token endpoint 時解密。

金鑰來自環境變數 GCAL_TOKEN_FERNET_KEY。金鑰遺失＝密文無法解密，只能重新授權。
錯誤訊息只說明「金鑰缺漏／格式不對／解不開」，絕不帶明文或密文。
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SecretBoxError(Exception):
    """加解密失敗（訊息安全，可直接回報給管理員）。"""


def _fernet() -> Fernet:
    key = (settings.GCAL_TOKEN_FERNET_KEY or "").strip()
    if not key:
        raise SecretBoxError("缺少環境變數 GCAL_TOKEN_FERNET_KEY（Fernet 金鑰）")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise SecretBoxError("GCAL_TOKEN_FERNET_KEY 格式不正確（需為 32 bytes 的 URL-safe base64）") from None


def is_configured() -> bool:
    try:
        _fernet()
        return True
    except SecretBoxError:
        return False


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise SecretBoxError("無法解密（金鑰不符或資料毀損），請重新連結 Google") from None
