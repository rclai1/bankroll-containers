"""Database-backed API for users and the leaderboard."""

import os
import secrets
import hashlib
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Identity,
    create_engine,
    text,
)

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
connection = os.getenv("CONNECTION")
if not connection:
    raise RuntimeError("CONNECTION was not found in the project .env file")

# TimescaleDB is PostgreSQL-compatible; map the two common PostgreSQL URL
# schemes to the SQLAlchemy TimescaleDB dialect without mangling the suffix.
if connection.startswith("postgresql://"):
    connection_url = "timescaledb://" + connection.removeprefix("postgresql://")
elif connection.startswith("postgres://"):
    connection_url = "timescaledb://" + connection.removeprefix("postgres://")
else:
    connection_url = connection
engine = create_engine(connection_url, pool_pre_ping=True)

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("balance", BigInteger, nullable=False),
    Column("username", String(50), nullable=False, unique=True),
    Column("password", Text, nullable=False),
    Column("salt", Text, nullable=False),
    Column("gray", SmallInteger, nullable=False, server_default="0"),
    Column("blue", SmallInteger, nullable=False, server_default="0"),
    Column("yellow", SmallInteger, nullable=False, server_default="0"),
    Column("green", SmallInteger, nullable=False, server_default="0"),
    Column("fade", SmallInteger, nullable=False, server_default="0"),
    Column("ancient", SmallInteger, nullable=False, server_default="0"),
    Column("maze", SmallInteger, nullable=False, server_default="0"),
    Column("stars", SmallInteger, nullable=False, server_default="0"),
    Column("wedges", SmallInteger, nullable=False, server_default="0"),
    Column("transit", SmallInteger, nullable=False, server_default="0"),
    Column("equipped_skin", String(16), nullable=False, server_default="default"),
)
games = Table(
    "games",
    metadata,
    Column("id", Integer, Identity(always=True), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("curr_money", Float, nullable=False),
    Column("cash_out", Boolean, nullable=False, default=False),
)
high_scores = Table(
    "high_scores",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("score", Float, nullable=False),
    UniqueConstraint("user_id", name="uq_high_scores_user_id"),
)
seed_table = Table(
    "seeds",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("seed", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

router = APIRouter()


class CreateHighScoreRequest(BaseModel):
    user_id: int = Field(gt=0)
    score: float = Field(ge=0, allow_inf_nan=False)


def create_tables() -> None:
    """Create the API tables if this is a fresh database."""
    metadata.create_all(engine)
    # Add shop fields to databases created before the card shop existed.
    with engine.begin() as connection:
        for name in ("gray", "blue", "yellow", "green", "fade", "ancient", "maze", "stars", "wedges", "transit"):
            connection.execute(text(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS "{name}" SMALLINT NOT NULL DEFAULT 0'))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS equipped_skin VARCHAR(16) NOT NULL DEFAULT 'default'"))


CARD_SKINS = ("gray", "blue", "yellow", "green", "fade", "ancient", "maze", "stars", "wedges", "transit")
COMMON_SKINS = CARD_SKINS[:4]
RARE_SKINS = CARD_SKINS[4:]
SHOP_COST = 10


def _shop_user(connection, session_token: str | None, *, lock: bool = False):
    if not session_token:
        raise HTTPException(status_code=401, detail="Sign in to use the card shop")
    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    suffix = " FOR UPDATE" if lock else ""
    user = connection.execute(text(
        "SELECT users.id, users.balance, users.equipped_skin, "
        + ", ".join(f'users."{name}"' for name in CARD_SKINS)
        + " FROM users JOIN auth_sessions ON users.id = auth_sessions.user_id "
        "WHERE auth_sessions.token_hash = :token_hash AND auth_sessions.expires_at > :now" + suffix
    ), {"token_hash": token_hash, "now": datetime.now(timezone.utc)}).mappings().one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to use the card shop")
    return user


def _shop_payload(user):
    return {"balance": user["balance"], "equipped_skin": user["equipped_skin"],
            "owned": ["default"] + [name for name in CARD_SKINS if user[name] == 1]}


@router.get("/shop")
def get_shop(bankroll_session: str | None = Cookie(default=None)):
    with engine.connect() as connection:
        return _shop_payload(_shop_user(connection, bankroll_session))


@router.post("/shop/roll")
def roll_shop(bankroll_session: str | None = Cookie(default=None)):
    with engine.begin() as connection:
        user = _shop_user(connection, bankroll_session, lock=True)
        if user["balance"] < SHOP_COST:
            raise HTTPException(status_code=409, detail="Not enough aircoin")
        result = random.choices(("nothing", "common", "rare"), weights=(80, 15, 5), k=1)[0]
        reward = random.choice(COMMON_SKINS if result == "common" else RARE_SKINS) if result != "nothing" else None
        duplicate = bool(reward and user[reward] == 1)
        refund = SHOP_COST if duplicate else 0
        connection.execute(text(
            "UPDATE users SET balance = balance - :cost + :refund"
            + (f', "{reward}" = 1' if reward else "")
            + " WHERE id = :user_id"
        ), {"cost": SHOP_COST, "refund": refund, "user_id": user["id"]})
        updated = _shop_user(connection, bankroll_session)
        return {**_shop_payload(updated), "result": result, "reward": reward,
                "duplicate": duplicate, "refund": refund}


class EquipSkinRequest(BaseModel):
    skin: str


@router.post("/shop/equip")
def equip_shop_skin(request: EquipSkinRequest, bankroll_session: str | None = Cookie(default=None)):
    if request.skin != "default" and request.skin not in CARD_SKINS:
        raise HTTPException(status_code=400, detail="Unknown card skin")
    with engine.begin() as connection:
        user = _shop_user(connection, bankroll_session, lock=True)
        if request.skin != "default" and user[request.skin] != 1:
            raise HTTPException(status_code=403, detail="You do not own this card skin")
        connection.execute(text("UPDATE users SET equipped_skin = :skin WHERE id = :user_id"), {"skin": request.skin, "user_id": user["id"]})
        updated = _shop_user(connection, bankroll_session)
        return _shop_payload(updated)


def _current_seed_reset(now: datetime) -> datetime:
    """Return the current daily reset boundary: 09:00 UTC (4:00 AM EST, 5:00 AM during daylight saving)."""
    reset = now.astimezone(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    if now.astimezone(timezone.utc) < reset:
        reset -= timedelta(days=1)
    return reset


@router.get("/seed")
def get_seed():
    """Return the singleton seed for the current daily period.

    A period starts at 09:00 UTC (4:00 AM EST; 5:00 AM during daylight saving).
    The first call after a reset creates a new seed, resets every player's daily
    progress, and clears the leaderboard (``high_scores``).
    """
    now = datetime.now(timezone.utc)
    reset_at = _current_seed_reset(now)
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """INSERT INTO seeds (id, seed, created_at)
                   VALUES (1, :seed, :created_at)
                   ON CONFLICT (id) DO UPDATE
                   SET seed = EXCLUDED.seed, created_at = EXCLUDED.created_at
                   WHERE seeds.created_at <> :reset_at
                   RETURNING seed, created_at"""
            ),
            {
                "seed": secrets.randbits(63),
                "created_at": reset_at,
                "reset_at": reset_at,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            row = connection.execute(
                text("SELECT seed, created_at FROM seeds WHERE id = 1")
            ).mappings().one()
        else:
            # Reset daily progress and leaderboard only when this call creates a new seed.
            connection.execute(text("UPDATE games SET cash_out = FALSE, curr_money = 100"))
            connection.execute(text("DELETE FROM high_scores"))
        return dict(row)


@router.get("/daily/{user_id}")
def get_daily_game(user_id: int):
    """Load or create the user's daily bankroll using the current daily seed."""
    seed_row = get_seed()
    with engine.begin() as connection:
        user_exists = connection.execute(
            text("SELECT 1 FROM users WHERE id = :user_id"), {"user_id": user_id}
        ).scalar_one_or_none()
        if user_exists is None:
            raise HTTPException(status_code=404, detail="User not found")
        row = connection.execute(
            text("SELECT id, curr_money, cash_out FROM games WHERE user_id = :user_id ORDER BY id DESC LIMIT 1 FOR UPDATE"),
            {"user_id": user_id},
        ).mappings().one_or_none()
        if row is None:
            row = connection.execute(
                text("INSERT INTO games (user_id, curr_money, cash_out) VALUES (:user_id, 100, FALSE) RETURNING id, curr_money, cash_out"),
                {"user_id": user_id},
            ).mappings().one()
        return {**dict(row), "seed": seed_row["seed"]}


@router.post("/daily/{user_id}/cashout")
def cash_out_daily_game(user_id: int):
    """Lock the daily session, award its completion bonus, and return its score."""
    with engine.begin() as connection:
        result = connection.execute(
            text("UPDATE games SET cash_out = TRUE WHERE id = (SELECT id FROM games WHERE user_id = :user_id ORDER BY id DESC LIMIT 1) AND cash_out = FALSE RETURNING curr_money"),
            {"user_id": user_id},
        ).scalar_one_or_none()
        reward = 0
        if result is None:
            row = connection.execute(
                text("SELECT curr_money, cash_out FROM games WHERE user_id = :user_id ORDER BY id DESC LIMIT 1"),
                {"user_id": user_id},
            ).mappings().one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="Daily game not found")
            if not row["cash_out"]:
                raise HTTPException(status_code=409, detail="Could not cash out daily game")
            result = row["curr_money"]
        elif result > 0:
            connection.execute(
                text("UPDATE users SET balance = balance + 100 WHERE id = :user_id"),
                {"user_id": user_id},
            )
            reward = 100
        return {"score": result, "cash_out": True, "reward": reward}


def save_daily_score(game_id: int, score: float) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            text("UPDATE games SET curr_money = :score WHERE id = :game_id AND cash_out = FALSE"),
            {"score": score, "game_id": game_id},
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="Daily game is already cashed out")


@router.post("/high_scores", status_code=201)
def create_high_score(request: CreateHighScoreRequest):
    """Create or replace this user's single high score."""
    with engine.begin() as connection:
        user_exists = connection.execute(
            text("SELECT 1 FROM users WHERE id = :user_id"), {"user_id": request.user_id}
        ).scalar_one_or_none()
        if user_exists is None:
            raise HTTPException(status_code=404, detail="User not found")

        # The unique user_id constraint makes the upsert atomic and guarantees
        # no user can have more than one row in high_scores.
        result = connection.execute(
            text(
                """INSERT INTO high_scores (user_id, score)
                   VALUES (:user_id, :score)
                   ON CONFLICT (user_id) DO UPDATE SET score = EXCLUDED.score
                   RETURNING id, user_id, score"""
            ),
            {"user_id": request.user_id, "score": request.score},
        )
        return dict(result.mappings().one())


@router.get("/high_scores")
def list_high_scores():
    """Return scores from highest to lowest, with their usernames."""
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """SELECT high_scores.id, high_scores.user_id, users.username, high_scores.score
                   FROM high_scores
                   JOIN users ON users.id = high_scores.user_id
                   ORDER BY high_scores.score DESC, high_scores.id ASC"""
            )
        )
        return [dict(row) for row in result.mappings()]
