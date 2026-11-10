import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services.phase10_experiment import run_experiment_dry_run

async def main():
    result = await run_experiment_dry_run()
    print("=== PHASE 10 EXPERIMENT PREFLIGHT REPORT ===")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

