from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from base64 import urlsafe_b64encode

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,80}$")
_ph = PasswordHasher()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Benutzername muss 3-80 Zeichen enthalten und darf nur Buchstaben, Ziffern, .-_ enthalten")
    return username.lower()


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise ValueError("Passwort muss 12 bis 128 Zeichen lang sein")
    if not re.search(r"[A-Za-zÄÖÜäöüß]", password) or not re.search(r"\d", password):
        raise ValueError("Passwort muss mindestens einen Buchstaben und eine Zahl enthalten")


def hash_password(password: str) -> str:
    validate_password(password)
    return _ph.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _ph.verify(encoded, password)
    except Exception:
        return False


def random_token(bytes_len: int = 32) -> str:
    return secrets.token_urlsafe(bytes_len)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def _fernet(master_key: str) -> Fernet:
    digest = hashlib.sha256(master_key.encode("utf-8")).digest()
    return Fernet(urlsafe_b64encode(digest))


def encrypt_secret(value: str, master_key: str) -> str:
    return _fernet(master_key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, master_key: str) -> str:
    return _fernet(master_key).decrypt(value.encode("ascii")).decode("utf-8")
