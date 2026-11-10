import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.adapters.apify import ApifyProviderAdapter
from app.core.database import async_session_factory
from app.core.config import get_settings

async def main():
    settings = get_settings()
    print("Daily limit:", settings.apify_daily_budget_usd)
    print("Monthly limit:", settings.apify_monthly_budget_usd)
    async with async_session_factory() as session:
        adapter = ApifyProviderAdapter(db=session)
        can_run, msg = await adapter._check_budget(1.80)
        print("Can reserve $1.80?", can_run, "Msg:", msg)

if __name__ == "__main__":
    asyncio.run(main())

