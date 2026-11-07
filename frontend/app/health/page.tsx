"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type H = {
  total_advertisers: number;
  total_advertisements: number;
  total_products: number;
  total_clusters: number;
  failed_jobs_24h: number;
  sources: {
    id: string;
    name: string;
    source_type: string;
    last_successful_collection: string | null;
    notes: string | null;
    config: { is_synthetic?: boolean } | null;
  }[];
  recent_runs: {
    id: string;
    status: string;
    started_at: string | null;
    records_fetched: number;
    records_new: number;
    records_duplicate: number;
    errors: unknown;
  }[];
};

type DiscoveryStatus = {
  status: string;
  configured: boolean;
  primary_actor: string;
  daily_budget_usd: number;
  monthly_budget_usd: number;
  estimated_spent_today_usd: number;
  estimated_spent_month_usd: number;
};

export default function Health() {
  const [h, setH] = useState<H | null>(null);
  const [disc, setDisc] = useState<DiscoveryStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<H>("/health/data"),
      api<DiscoveryStatus>("/discovery/status").catch(() => null),
    ])
      .then(([healthData, discData]) => {
        setH(healthData);
        if (discData) setDisc(discData);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="text-red-600">Backend unreachable: {err}</p>;
  if (!h) return <p>Loading…</p>;

  const hasSynthetic = h.sources.some((s) => s.config?.is_synthetic);
  const totalRuns = h.recent_runs.length;
  const failedRuns = h.recent_runs.filter((r) => r.status === "failed").length;
  const errorRate = totalRuns > 0 ? Math.round((failedRuns / totalRuns) * 100) : 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Data Health & Provenance</h1>
          <p className="text-xs text-slate-500">
            Real vs synthetic source tracking, provider health, and collection pipeline metrics.
          </p>
        </div>
        {disc && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Live Provider Status:</span>
            <span
              className={`px-2 py-0.5 text-xs font-semibold rounded ${
                disc.status === "READY"
                  ? "bg-emerald-100 text-emerald-800"
                  : disc.status === "NOT_CONFIGURED"
                  ? "bg-amber-100 text-amber-800"
                  : "bg-red-100 text-red-800"
              }`}
            >
              {disc.status}
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {[
          ["Advertisers", h.total_advertisers],
          ["Live Ads", h.total_advertisements],
          ["Products", h.total_products],
          ["Clusters", h.total_clusters],
          ["Error Rate", `${errorRate}%`],
          ["Failed Runs (24h)", h.failed_jobs_24h],
        ].map(([l, v]) => (
          <div key={l as string} className="bg-white rounded shadow p-3">
            <div className="text-xs text-slate-500">{l}</div>
            <div className="text-lg font-semibold">{v}</div>
          </div>
        ))}
      </div>

      {hasSynthetic && (
        <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded">
          <span className="font-bold">Provenance Notice:</span> The database contains synthetic demo records.
          Live discovery and real Apify dataset imports are segregated from demo data.
        </div>
      )}

      <section className="bg-white rounded shadow p-4 space-y-3">
        <h2 className="font-semibold text-sm">Registered Data Sources & Provenance</h2>
        {h.sources.length === 0 ? (
          <p className="text-sm text-slate-500">
            No sources yet. No live integrations are configured.
          </p>
        ) : (
          <ul className="text-xs space-y-2">
            {h.sources.map((s) => (
              <li key={s.id} className="p-2 border rounded flex items-center justify-between">
                <div>
                  <span className="font-bold text-slate-800">{s.name}</span>
                  <span className="ml-2 font-mono text-slate-500 text-[11px]">({s.source_type})</span>
                  {s.config?.is_synthetic ? (
                    <span className="ml-2 rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">
                      SYNTHETIC DEMO
                    </span>
                  ) : (
                    <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800">
                      LIVE REAL
                    </span>
                  )}
                </div>
                <div className="text-slate-500 text-[11px]">
                  Last Success: {s.last_successful_collection?.slice(0, 19) ?? "never"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="bg-white rounded shadow p-4 space-y-3">
        <h2 className="font-semibold text-sm">Recent Collection Runs</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-left text-slate-600 font-semibold border-b">
              <tr>
                <th className="p-2">Started</th>
                <th className="p-2">Status</th>
                <th className="p-2">Fetched</th>
                <th className="p-2">New Valid</th>
                <th className="p-2">Duplicates</th>
                <th className="p-2">Errors / Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {h.recent_runs.map((r) => (
                <tr key={r.id}>
                  <td className="p-2 font-mono">{r.started_at?.slice(0, 19) ?? "—"}</td>
                  <td className="p-2">
                    <span
                      className={`px-1.5 py-0.5 rounded font-semibold ${
                        r.status === "completed"
                          ? "bg-emerald-100 text-emerald-800"
                          : r.status === "running"
                          ? "bg-blue-100 text-blue-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="p-2 font-mono">{r.records_fetched}</td>
                  <td className="p-2 font-mono text-emerald-700 font-semibold">{r.records_new}</td>
                  <td className="p-2 font-mono text-slate-500">{r.records_duplicate}</td>
                  <td className="p-2 text-slate-600 max-w-xs truncate">
                    {r.errors ? JSON.stringify(r.errors) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
