"""Application entry point for the Bankroll API.

Run from the ``backend/`` folder (not from ``backend/app``), because this module
uses package-relative imports::

    uvicorn app.main:app --reload --port 8000
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.blackjack_api import router as blackjack_router
from .routers.auth_endpoints import router as auth_router
from .routers.database import create_tables, router as database_router


app = FastAPI(title="Bankroll API", version="1.0.0")
configured_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
allowed_origins = sorted({
    "http://localhost:3000",
    "https://bankroll-rclj-736dmvlsg-reed-lais-projects.vercel.app",
    *configured_origins,
})
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(database_router)
app.include_router(auth_router)
app.include_router(blackjack_router)

# Docker Compose's Next.js rewrites remove the public `/api` prefixes before
# forwarding requests. Vercel Services can forward the original path instead,
# so expose aliases that also accept those public paths directly.
app.include_router(auth_router, prefix="/api")
app.include_router(blackjack_router, prefix="/api/blackjack")
app.include_router(database_router, prefix="/api/blackjack")
app.include_router(database_router, prefix="/api")


@app.on_event("startup")
def initialize_database() -> None:
    create_tables()
