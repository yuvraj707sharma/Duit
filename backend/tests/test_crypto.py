"""Tests for AES-256-GCM Token Encryption, AAD Binding, and Key Versioning."""
import pytest
import base64
from backend.app.security.crypto import (
    validate_encryption_key,
    encrypt_token,
    decrypt_token,
    CryptoKeyError
)


def test_crypto_valid_32_byte_base64_key():
    # 32 raw bytes encoded in base64
    valid_key = base64.b64encode(b"0" * 32).decode("utf-8")
    raw = validate_encryption_key(valid_key)
    assert len(raw) == 32


def test_crypto_invalid_key_length_fails():
    short_key = base64.b64encode(b"too_short").decode("utf-8")
    with pytest.raises(CryptoKeyError):
        validate_encryption_key(short_key)

    invalid_b64 = "not-valid-base64!!!"
    with pytest.raises(CryptoKeyError):
        validate_encryption_key(invalid_b64)


def test_crypto_user_id_aad_binding():
    key_b64 = base64.b64encode(b"k" * 32).decode("utf-8")
    plain = "ya29.google_oauth_secret_refresh_token_12345"
    
    # Encrypt bound to user_101
    encrypted = encrypt_token(plain, user_id="user_101", key_b64=key_b64)
    assert encrypted.startswith("v1:")

    # Decrypt with correct user_id
    decrypted = decrypt_token(encrypted, user_id="user_101", key_b64=key_b64)
    assert decrypted == plain

    # Decrypt with incorrect user_id MUST fail (AAD mismatch)
    with pytest.raises(Exception):
        decrypt_token(encrypted, user_id="attacker_user_999", key_b64=key_b64)


def test_crypto_version_prefix_enforced():
    key_b64 = base64.b64encode(b"v" * 32).decode("utf-8")
    encrypted = encrypt_token("secret", user_id="u1", key_b64=key_b64)
    assert encrypted.startswith("v1:")

    # Payload without v1 prefix should fail
    with pytest.raises(ValueError):
        decrypt_token(encrypted[3:], user_id="u1", key_b64=key_b64)
