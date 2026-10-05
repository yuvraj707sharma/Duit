"""AES-256-GCM Encryption and Decryption for sensitive tokens with AAD binding and key versioning."""
import os
import base64
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from backend.app.config import settings


class CryptoKeyError(ValueError):
    """Raised when encryption key is missing or not a 32-byte base64 string."""
    pass


def validate_encryption_key(key_b64: Optional[str] = None) -> bytes:
    """Validates that key is exactly 32 raw bytes encoded in base64."""
    key_str = key_b64 or settings.TOKEN_ENCRYPTION_KEY
    if not key_str:
        raise CryptoKeyError("TOKEN_ENCRYPTION_KEY environment variable is missing.")

    try:
        raw_key = base64.b64decode(key_str, validate=True)
    except Exception as e:
        raise CryptoKeyError(f"Invalid base64 encoding for TOKEN_ENCRYPTION_KEY: {e}") from e

    if len(raw_key) != 32:
        raise CryptoKeyError(
            f"TOKEN_ENCRYPTION_KEY must be exactly 32 bytes (256 bits) when decoded; got {len(raw_key)} bytes."
        )
    return raw_key


def encrypt_token(plain_token: str, user_id: str, key_b64: Optional[str] = None) -> str:
    """Encrypts plaintext token using AES-256-GCM with AAD bound to user_id and v1 prefix."""
    if not plain_token:
        return ""
    if not user_id:
        raise ValueError("user_id is required to bind authenticated data (AAD).")

    key = validate_encryption_key(key_b64)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    aad = f"v1:{user_id}".encode("utf-8")
    
    ciphertext = aesgcm.encrypt(nonce, plain_token.encode("utf-8"), aad)
    payload_b64 = base64.b64encode(nonce + ciphertext).decode("utf-8")
    return f"v1:{payload_b64}"


def decrypt_token(encrypted_token: str, user_id: str, key_b64: Optional[str] = None) -> str:
    """Decrypts AES-256-GCM payload with AAD verification bound to user_id."""
    if not encrypted_token:
        return ""
    if not user_id:
        raise ValueError("user_id is required to verify authenticated data (AAD).")

    if not encrypted_token.startswith("v1:"):
        raise ValueError("Unsupported key version prefix. Expected 'v1:'.")

    payload_b64 = encrypted_token[3:]
    key = validate_encryption_key(key_b64)
    aesgcm = AESGCM(key)
    
    payload = base64.b64decode(payload_b64.encode("utf-8"))
    if len(payload) < 28:  # 12-byte nonce + 16-byte GCM tag
        raise ValueError("Ciphertext payload is truncated or corrupted.")

    nonce = payload[:12]
    ciphertext = payload[12:]
    aad = f"v1:{user_id}".encode("utf-8")

    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
    return decrypted_bytes.decode("utf-8")
