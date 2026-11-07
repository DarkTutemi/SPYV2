"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type DiscoveryStatus = {
  status: string;
  configured: boolean;
  primary_actor: string;
  fallback_actor: string;
  daily_budget_usd: number;
  monthly_budget_usd: number;
  estimated_spent_today_usd: number;
  estimated_spent_month_usd: number;
  auto_collection_enabled: boolean;
  message: string;
  scheduler_status?: {
    running: boolean;
    collection_running: boolean;
    last_run: string | null;
    last_collection: string | null;
    interval_minutes: number;
    scheduler_active: boolean;
  };
};

export default function SettingsPage() {
  const [discStatus, setDiscStatus] = useState<DiscoveryStatus | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<"primary" | "fallback">("primary");
  const [dailyBudget, setDailyBudget] = useState<number>(5.0);
  const [monthlyBudget, setMonthlyBudget] = useState<number>(50.0);
  const [autoCollect, setAutoCollect] = useState<boolean>(false);
  const [isTriggering, setIsTriggering] = useState<boolean>(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  const [emergenceWeights] = useState({
    "Independent advertiser acceleration": 0.30,
    "New creative acceleration": 0.25,
    "Ad persistence (sustained investment)": 0.20,
    "Signal recency": 0.15,
    "Non-ad demand confirmation": 0.10,
  });

  const [confidenceWeights] = useState({
    "Temporal data coverage completeness": 0.30,
    "Independent source corroboration": 0.25,
    "Product identity certainty": 0.20,
    "Advertiser independence verification": 0.15,
    "Verifiable evidence links": 0.10,
  });

  const [bundleWeights] = useState({
    "Natural multi-unit necessity": 0.30,
    "Functional benefit of multiple units": 0.25,
    "AOV fit ($30–$90 USD window)": 0.20,
    "Usage frequency / rotation pattern": 0.15,
    "Decision simplicity": 0.10,
  });

  useEffect(() => {
    api<DiscoveryStatus>("/discovery/status")
      .then((res) => {
        setDiscStatus(res);
        setDailyBudget(res.daily_budget_usd);
        setMonthlyBudget(res.monthly_budget_usd);
        setAutoCollect(res.auto_collection_enabled);
      })
      .catch((e) => console.warn("Failed to load discovery status", e));
  }, []);

  const handleManualTrigger = async () => {
    setIsTriggering(true);
    setTriggerMsg(null);
    try {
      const res = await api<{ success: boolean; status?: string; records_valid?: number; error?: string }>("/discovery/run", {
        method: "POST",
        body: JSON.stringify({
          max_ads: 30,
          use_fallback: selectedProvider === "fallback",
          force: true,
        }),
      });
      if (res.success) {
        setTriggerMsg(`Discovery run completed: ${res.records_valid ?? 0} valid US ads processed.`);
      } else {
        setTriggerMsg(`Discovery run stopped: ${res.error || res.status}`);
      }
    } catch (e: any) {
      setTriggerMsg(`Error: ${e.message || String(e)}`);
    } finally {
      setIsTriggering(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">System Configuration & Settings</h1>
        <p className="text-xs text-slate-500 mt-1">
          Review live data provider settings, budget limits, collection schedules, and scoring weights.
        </p>
      </div>

      {/* Live Provider & Budget Settings */}
      <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <div>
            <h2 className="text-base font-semibold text-slate-800">
              Live Data Provider & Budget Guardrails
            </h2>
            <p className="text-xs text-slate-500">Autonomous Meta Ad Library collection via Apify actors</p>
          </div>
          <span
            className={`px-2.5 py-1 text-xs font-semibold rounded ${
              discStatus?.status === "READY"
                ? "bg-emerald-100 text-emerald-800"
                : discStatus?.status === "NOT_CONFIGURED"
                ? "bg-amber-100 text-amber-800"
                : "bg-red-100 text-red-800"
            }`}
          >
            {discStatus?.status || "CHECKING"}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="space-y-3">
            <div>
              <label className="font-semibold text-slate-700 block mb-1">Active Live Provider</label>
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value as "primary" | "fallback")}
                className="w-full border rounded p-2 text-xs bg-slate-50"
              >
                <option value="primary">
                  Primary: {discStatus?.primary_actor || "automation-lab/facebook-ads-library"}
                </option>
                <option value="fallback">
                  Fallback: {discStatus?.fallback_actor || "curious_coder/facebook-ads-library-scraper"}
                </option>
              </select>
            </div>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">Apify API Authentication</label>
              <div className="p-2.5 rounded bg-slate-50 border flex items-center justify-between">
                <span className="font-mono text-slate-600">
                  {discStatus?.configured ? "Token loaded from env (APIFY_API_TOKEN)" : "Token missing from .env"}
                </span>
                <span className={discStatus?.configured ? "text-emerald-600 font-bold" : "text-amber-600 font-bold"}>
                  {discStatus?.configured ? "AUTHENTICATED" : "NOT CONFIGURED"}
                </span>
              </div>
            </div>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">Autonomous Collection Schedule</label>
              <div className="p-2.5 rounded bg-slate-50 border text-slate-600 space-y-1">
                <div>Interval: Every {discStatus?.scheduler_status?.interval_minutes || 360} minutes (6 hours)</div>
                <div>Status: {discStatus?.scheduler_status?.scheduler_active ? "Active In-Process Loop" : "Idle"}</div>
                <div>Last Run: {discStatus?.scheduler_status?.last_run?.slice(0, 19) || "Never"}</div>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div>
              <label className="font-semibold text-slate-700 block mb-1">Hard Spend Caps (Fail-Closed)</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-slate-500 text-[11px]">Daily Max USD</span>
                  <input
                    type="number"
                    value={dailyBudget}
                    onChange={(e) => setDailyBudget(Number(e.target.value))}
                    className="w-full border rounded p-1.5 text-xs font-mono"
                  />
                </div>
                <div>
                  <span className="text-slate-500 text-[11px]">Monthly Max USD</span>
                  <input
                    type="number"
                    value={monthlyBudget}
                    onChange={(e) => setMonthlyBudget(Number(e.target.value))}
                    className="w-full border rounded p-1.5 text-xs font-mono"
                  />
                </div>
              </div>
            </div>

            <div className="p-2.5 rounded bg-slate-50 border space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-600">Spent Today:</span>
                <span className="font-mono font-bold">${discStatus?.estimated_spent_today_usd ?? "0.00"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-600">Spent This Month:</span>
                <span className="font-mono font-bold">${discStatus?.estimated_spent_month_usd ?? "0.00"}</span>
              </div>
            </div>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">Auto-Collection Toggle</label>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="autoCollectToggle"
                  checked={autoCollect}
                  onChange={(e) => setAutoCollect(e.target.checked)}
                  className="rounded border-slate-300"
                />
                <label htmlFor="autoCollectToggle" className="text-slate-700">
                  Allow automatic paid runs during scheduled cycles (Default: Disabled)
                </label>
              </div>
            </div>

            <div className="pt-1">
              <button
                onClick={handleManualTrigger}
                disabled={isTriggering}
                className="w-full py-2 bg-slate-900 text-white rounded font-medium hover:bg-slate-800 disabled:opacity-50 text-xs"
              >
                {isTriggering ? "Running Live Discovery…" : "Run Bounded Discovery Now (1 Seed Query)"}
              </button>
              {triggerMsg && <p className="text-xs mt-2 text-slate-700 font-medium">{triggerMsg}</p>}
            </div>
          </div>
        </div>
      </div>

      {/* Weights Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Emergence */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="border-b pb-2">
            <h2 className="font-bold text-slate-800 text-sm">Emergence Weights (0–100)</h2>
            <p className="text-[11px] text-slate-400">Advertising momentum signal</p>
          </div>
          <div className="space-y-2">
            {Object.entries(emergenceWeights).map(([name, weight]) => (
              <div key={name} className="text-xs flex justify-between items-center">
                <span className="text-slate-600 truncate mr-2">{name}</span>
                <span className="font-mono font-semibold bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">
                  {Math.round(weight * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Confidence */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="border-b pb-2">
            <h2 className="font-bold text-slate-800 text-sm">Evidence Confidence (0–100)</h2>
            <p className="text-[11px] text-slate-400">Data completeness & reliability</p>
          </div>
          <div className="space-y-2">
            {Object.entries(confidenceWeights).map(([name, weight]) => (
              <div key={name} className="text-xs flex justify-between items-center">
                <span className="text-slate-600 truncate mr-2">{name}</span>
                <span className="font-mono font-semibold bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">
                  {Math.round(weight * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Bundle */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="border-b pb-2">
            <h2 className="font-bold text-slate-800 text-sm">Bundle Potential (0–100)</h2>
            <p className="text-[11px] text-slate-400">Multi-unit & $30–$90 AOV fit</p>
          </div>
          <div className="space-y-2">
            {Object.entries(bundleWeights).map(([name, weight]) => (
              <div key={name} className="text-xs flex justify-between items-center">
                <span className="text-slate-600 truncate mr-2">{name}</span>
                <span className="font-mono font-semibold bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">
                  {Math.round(weight * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
