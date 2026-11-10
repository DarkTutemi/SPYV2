import asyncio
import os
import sys

# Ensure backend is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import async_session_factory
from app.services.phase10_experiment import Phase10ExperimentService


async def main():
    print("=" * 70)
    print("US WIN HUNTER — AUTHORIZED LIVE EXPERIMENT EXECUTION")
    print("Phase 10: 14 Tasks | Country: US | Max Spend Cap: $0.50 USD")
    print("=" * 70)

    async with async_session_factory() as session:
        service = Phase10ExperimentService(session)
        print("Running preflight safety check...")
        preflight = await service.run_preflight_checks()
        if not preflight.is_ready:
            print(f"ABORT: Preflight check failed: {preflight.notes}")
            return 1

        print(f"Preflight OK. Estimated Cost: ${preflight.estimated_cost_usd:.4f} USD.")
        print(f"Safety Buffer: {preflight.safety_buffer_ratio}x.")
        print("Starting 14 sequential tasks execution now...")

        report = await service.run_full_experiment()

        print("\n" + "=" * 70)
        print("EXPERIMENT COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print(f"Experiment Run ID:     {report['experiment_run_id']}")
        print(f"Tasks Executed:        {report['total_tasks_run']}/14")
        print(f"Total Billed USD:      ${report['total_billed_usd']:.4f} USD")
        print(f"Total Ads Collected:   {report['total_ads_collected']}")
        print(f"Unique Commercial Ads: {report['total_unique_ads']}")
        print(f"Unique Products:       {report['total_unique_products']}")
        print(f"Shortlisted Products:  {report['shortlist_count']}")
        print(f"Report Generated At:   {report['report_path']}")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code or 0)

