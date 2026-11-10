import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core import database
from app.core.config import get_settings

TEST_DB_URL = "sqlite+aiosqlite:///./test_winhunter.db"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["DEBUG"] = "false"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
database.engine = test_engine
database.async_session_factory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
