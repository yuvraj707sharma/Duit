"""AES-256-GCM encryption & decryption for standalone Desktop Sidecar."""
import os
import base64
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_KEY = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="


def validate_encryption_key(key_b64: Optional[str] = None) -> bytes:
    key_str = key_b64 or os.getenv("TOKEN_ENCRYPTION_KEY", DEFAULT_KEY)
    raw_key = base64.b64decode(key_str, validate=True)
    if len(raw_key) != 32:
        raise ValueError(f"TOKEN_ENCRYPTION_KEY must be exactly 32 bytes; got {len(raw_key)} bytes.")
    return raw_key


def encrypt_token(plain_token: str, user_id: str, key_b64: Optional[str] = None) -> str:
    if not plain_token:
        return ""
    key = validate_encryption_key(key_b64)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    aad = f"v1:{user_id}".encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plain_token.encode("utf-8"), aad)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_token(encrypted_payload: str, user_id: str, key_b64: Optional[str] = None) -> str:
    if not encrypted_payload:
        return ""
    key = validate_encryption_key(key_b64)
    aesgcm = AESGCM(key)
    raw_payload = base64.b64decode(encrypted_payload, validate=True)
    nonce, ciphertext = raw_payload[:12], raw_payload[12:]
    aad = f"v1:{user_id}".encode("utf-8")
    decrypted = aesgcm.decrypt(nonce, ciphertext, aad)
    return decrypted.decode("utf-8")
