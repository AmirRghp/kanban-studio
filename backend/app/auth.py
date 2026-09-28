"""Password hashing with the stdlib only.

Format: `pbkdf2_sha256$iterations$salt_hex$hash_hex`. Naming the algorithm in the
stored string means the cost can be raised later without a migration.
"""

import hashlib
import secrets

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

# 240k iterations lands around 100 ms per verify on the container's hardware, which is
# standard practice for an interactive login.
ITERATIONS = 240_000

SESSION_COOKIE = "session"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison, so a wrong password cannot be told apart by timing."""
    try:
        algorithm, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
    ).hex()
    return secrets.compare_digest(digest, expected)


def validate_registration(username: str, password: str) -> str | None:
    """A reason the registration is invalid, or None when it is acceptable."""
    if not 3 <= len(username) <= 30:
        return "Username must be 3-30 characters."
    if not username.replace("-", "").replace("_", "").isalnum():
        return "Username may only contain letters, numbers, hyphens and underscores."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    return None


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class SessionUser(BaseModel):
    username: str


def require_user(request: Request) -> SessionUser:
    """Dependency for endpoints that need a signed-in user."""
    username = request.session.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in"
        )
    return SessionUser(username=username)
