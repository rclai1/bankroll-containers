"""Registration and login endpoints."""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .auth import hash_password, verify_password
from .database import auth_sessions, engine, users

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE = "bankroll_session"
SESSION_DAYS = 30


def _start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with engine.begin() as connection:
        connection.execute(
            auth_sessions.insert().values(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                user_id=user_id,
                expires_at=expires_at,
            )
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
        samesite="lax",
        path="/",
    )


def _clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


class CredentialsRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50, strip_whitespace=True)
    password: str = Field(min_length=8, max_length=1024)


@router.post("/register", status_code=201)
def register(request: CredentialsRequest, response: Response):
    """Create an account, storing a plain username and password hash."""
    password_fields = hash_password(request.password)
    try:
        with engine.begin() as connection:
            result = connection.execute(
                users.insert()
                .values(
                    username=request.username,
                    balance=10,
                    password=password_fields["password_hash"],
                    salt=password_fields["password_salt"],
                )
                .returning(users.c.id, users.c.username)
            )
            user = dict(result.mappings().one())
        _start_session(response, user["id"])
        return user
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username already exists") from exc


@router.post("/login")
def login(request: CredentialsRequest, response: Response):
    """Verify credentials and return the user's public account identity."""
    with engine.connect() as connection:
        user = connection.execute(
            select(users.c.id, users.c.username, users.c.password, users.c.salt)
            .where(users.c.username == request.username)
        ).mappings().one_or_none()

    if user is None or not verify_password(
        request.password, user["password"], user["salt"]
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    _start_session(response, user["id"])
    return {"id": user["id"], "username": user["username"]}


@router.get("/session")
def get_session(bankroll_session: str | None = Cookie(default=None)):
    if not bankroll_session:
        return None
    token_hash = hashlib.sha256(bankroll_session.encode()).hexdigest()
    with engine.begin() as connection:
        user = connection.execute(
            select(users.c.id, users.c.username)
            .join(auth_sessions, users.c.id == auth_sessions.c.user_id)
            .where(
                auth_sessions.c.token_hash == token_hash,
                auth_sessions.c.expires_at > datetime.now(timezone.utc),
            )
        ).mappings().one_or_none()
        if user is None:
            connection.execute(auth_sessions.delete().where(auth_sessions.c.token_hash == token_hash))
            return None
        return dict(user)


@router.post("/logout", status_code=204)
def logout(response: Response, bankroll_session: str | None = Cookie(default=None)):
    if bankroll_session:
        token_hash = hashlib.sha256(bankroll_session.encode()).hexdigest()
        with engine.begin() as connection:
            connection.execute(auth_sessions.delete().where(auth_sessions.c.token_hash == token_hash))
    _clear_session(response)
