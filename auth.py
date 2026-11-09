"""Аутентификация: хеширование паролей, проверка данных и серверные сессии.

Как это работает:
1. При входе сервер создаёт случайный токен и кладёт его в cookie (HttpOnly, поэтому JavaScript его не видит).
2. В базе хранится только SHA-256 от токена и срок действия.
3. На каждый запрос сервер берёт токен из cookie, находит сессию в базе и узнаёт пользователя.
4. При выходе сессия удаляется из базы, и токен перестаёт работать.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

import database

SESSION_COOKIE = "session"
SESSION_DAYS = 30  # cookie с max_age переживает перезапуск браузера
MIN_PASSWORD = 8
MAX_PASSWORD = 128
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Параметры scrypt: стандартная библиотека, ничего устанавливать не нужно.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


# --- Пароли ---


def hash_password(password: str) -> str:
    """Возвращает строку вида 'scrypt$соль$хеш'. Соль у каждого пароля своя."""
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = _scrypt(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))  # сравнение за постоянное время


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )


# Хеш для случая «такого email нет»: так вход тратит одно и то же время
# и по скорости ответа нельзя узнать, зарегистрирован ли адрес.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def check_credentials(email: str, password: str) -> dict | None:
    user = database.get_user_by_email(email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user["password_hash"]) else None


# --- Проверка данных ---


def normalize_email(email: str) -> str:
    return email.strip().lower()


def email_error(email: str) -> str | None:
    if not email:
        return "Укажите email."
    if len(email) > 254 or not EMAIL_RE.match(email):
        return "Введите корректный email, например name@example.com."
    return None


def password_error(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"Пароль должен быть не короче {MIN_PASSWORD} символов."
    if len(password) > MAX_PASSWORD:
        return f"Пароль должен быть не длиннее {MAX_PASSWORD} символов."
    if password.isdigit() or password.isalpha():
        return "Добавьте в пароль и буквы, и цифры (или другие символы)."
    return None


# --- Сессии ---


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(user_id: int) -> str:
    """Создаёт сессию в базе и возвращает токен для cookie."""
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    database.create_session(_token_hash(token), user_id, expires.strftime("%Y-%m-%d %H:%M:%S"))
    return token


def user_from_token(token: str | None) -> dict | None:
    return database.get_user_by_session(_token_hash(token)) if token else None


def end_session(token: str | None) -> None:
    if token:
        database.delete_session(_token_hash(token))


def end_other_sessions(user_id: int, token: str) -> None:
    database.delete_other_sessions(user_id, _token_hash(token))
