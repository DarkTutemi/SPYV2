import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.database import async_session_factory
from app.adapters.apify import ApifyProviderAdapter

async def check():
    async with async_session_factory() as session:
        adapter = ApifyProviderAdapter(db=session)
        spent_today, spent_month = await adapter._calculate_current_spend()
        print(f"Current spend: today=${spent_today:.4f}, month=${spent_month:.4f}")

if __name__ == "__main__":
    asyncio.run(check())

