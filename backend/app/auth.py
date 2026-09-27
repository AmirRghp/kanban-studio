import secrets

from fastapi import HTTPException, Request, status
from pydantic import BaseModel

# The MVP has a single hardcoded account, per the project brief. The users table in
# docs/DATA-MODEL.md exists so real accounts can replace this later.
VALID_USERNAME = "user"
VALID_PASSWORD = "password"

SESSION_COOKIE = "session"


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionUser(BaseModel):
    username: str


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time comparison, so a wrong username cannot be told apart by timing."""
    return secrets.compare_digest(username, VALID_USERNAME) and secrets.compare_digest(
        password, VALID_PASSWORD
    )


def require_user(request: Request) -> SessionUser:
    """Dependency for endpoints that need a signed-in user."""
    username = request.session.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in"
        )
    return SessionUser(username=username)
