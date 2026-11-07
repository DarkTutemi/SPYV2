"""
US WIN HUNTER — FastAPI Application Entry Point
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.api.routes import router as api_router


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger.info("US WIN HUNTER starting up (env=%s)", settings.app_env)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    yield

    logger.info("US WIN HUNTER shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="US WIN HUNTER — AI Product Intelligence Engine",
        description=(
            "Evidence-driven product discovery platform for finding emerging "
            "physical products in the US market with natural multi-unit bundle demand."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for Next.js frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routes
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()

