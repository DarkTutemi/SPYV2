import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.services.t14_monitoring import T14MonitoringService, ICT, T14_EXECUTION_THRESHOLD_ICT

now = datetime.now(timezone.utc)
now_ict = now.astimezone(ICT)

print(f"Current UTC time:        {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"Current Local (ICT) time:{now_ict.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"T+14 Target Threshold:   {T14_EXECUTION_THRESHOLD_ICT.strftime('%Y-%m-%d %H:%M:%S %Z')}")

eligible, msg = T14MonitoringService.check_execution_eligibility(current_time=now, operator_authorized=True)
print(f"Eligibility result:      {eligible}")
print(f"System Message:          {msg}")

remaining = T14_EXECUTION_THRESHOLD_ICT - now_ict
days = remaining.days
hours = remaining.seconds // 3600
minutes = (remaining.seconds % 3600) // 60
print(f"Time remaining:          {days} days, {hours} hours, {minutes} minutes")

