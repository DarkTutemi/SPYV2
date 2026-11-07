"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type H = {
  total_advertisers: number; total_advertisements: number; total_products: number; total_clusters: number; failed_jobs_24h: number;
  sources: { id: string; name: string; source_type: string; last_successful_collection: string | null; notes: string | null; config: { is_synthetic?: boolean } | null }[];
  recent_runs: { id: string; status: string; started_at: string | null; records_fetched: number; records_new: number; records_duplicate: number; errors: unknown }[];
};

export default function Health() {
  const [h, setH] = useState<H | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<H>("/health/data").then(setH).catch((e) => setErr(String(e))); }, []);
  if (err) return <p className="text-red-600">Backend unreachable: {err}</p>;
  if (!h) return <p>Loading…</p>;
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Data Health</h1>
      <div className="grid grid-cols-5 gap-3">
        {[["Advertisers", h.total_advertisers], ["Ads", h.total_advertisements], ["Products", h.total_products], ["Clusters", h.total_clusters], ["Failed runs 24h", h.failed_jobs_24h]].map(([l, v]) =>
          <div key={l as string} className="bg-white rounded shadow p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-lg font-semibold">{v}</div></div>)}
      </div>
      <section className="bg-white rounded shadow p-3">
        <h2 className="font-semibold mb-2">Sources</h2>
        {h.sources.length === 0 ? <p className="text-sm text-slate-500">No sources yet. No live integrations are configured — see docs/DATA_SOURCE_FEASIBILITY.md.</p> :
          <ul className="text-sm space-y-1">{h.sources.map((s) => <li key={s.id}>
            <b>{s.name}</b> {s.config?.is_synthetic && <span className="ml-1 rounded bg-amber-200 px-1 text-xs">SYNTHETIC DEMO</span>} · last success: {s.last_successful_collection?.slice(0, 19) ?? "never"}</li>)}</ul>}
      </section>
      <section className="bg-white rounded shadow p-3">
        <h2 className="font-semibold mb-2">Recent collection runs</h2>
        <table className="w-full text-sm"><thead className="text-left"><tr><th>Started</th><th>Status</th><th>Fetched</th><th>New</th><th>Duplicates</th><th>Errors</th></tr></thead>
          <tbody>{h.recent_runs.map((r) => <tr key={r.id} className="border-t"><td>{r.started_at?.slice(0, 19) ?? "—"}</td><td>{r.status}</td><td>{r.records_fetched}</td><td>{r.records_new}</td><td>{r.records_duplicate}</td><td>{r.errors ? JSON.stringify(r.errors) : "—"}</td></tr>)}</tbody></table>
      </section>
    </div>
  );
}

