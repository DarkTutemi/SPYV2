"""
US WIN HUNTER — Database engine and session management.

Supports both SQLite (local dev) and PostgreSQL (production).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def _create_engine():
    settings = get_settings()
    connect_args = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    return engine


engine = _create_engine()

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Create all tables. For development use — production should use Alembic."""
    async with engine.begin() as conn:
        # Enable WAL mode for SQLite
        if get_settings().is_sqlite:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)


async def drop_db():
    """Drop all tables. For testing only."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session scope."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

