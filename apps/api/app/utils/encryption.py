import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_key() -> bytes:
    raw = settings.ID_ENCRYPTION_KEY.encode()
    return hashlib.sha256(raw).digest()


def encrypt_national_id(plaintext: str) -> bytes:
    key = _get_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return nonce + ciphertext


def decrypt_national_id(data: bytes) -> str:
    key = _get_key()
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


def hmac_national_id(plaintext: str) -> str:
    key = _get_key()
    return hmac.new(key, plaintext.encode(), hashlib.sha256).hexdigest()
