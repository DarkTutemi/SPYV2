import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.database import async_session_factory
from sqlalchemy import select
from app.models.models import CollectionRun, CollectionJob, Product, SourceRecord, Advertisement

async def main():
    async with async_session_factory() as db:
        runs = (await db.execute(select(CollectionRun).order_by(CollectionRun.created_at.desc()).limit(20))).scalars().all()
        print(f"Total runs: {len(runs)}")
        for r in runs:
            err = r.errors
            if isinstance(err, str):
                try:
                    err = json.loads(err)
                except:
                    pass
            print(f"Run ID: {r.id[:8]} | status: {r.status} | fetched: {r.records_fetched} | err_type: {type(err)} | err: {err}")

if __name__ == "__main__":
    asyncio.run(main())
