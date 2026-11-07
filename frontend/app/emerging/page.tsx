"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type E = { product_id: string; product_name: string; acceleration: number; window_days: number; coverage_warning: string | null };

export default function EmergingRadar() {
  const [rows, setRows] = useState<E[] | null>(null);
  const [window, setWindow] = useState(7);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => { setRows(null); api<E[]>(`/temporal/emerging?window=${window}`).then(setRows).catch((e) => setErr(String(e))); };
  useEffect(() => { load(); }, [window]);

  const runPipeline = async () => {
    setBusy(true);
    try {
      await api("/temporal/snapshot", { method: "POST" });
      await api("/temporal/aggregate", { method: "POST" });
      await api("/scores/compute", { method: "POST" });
      await api("/temporal/graph/discover", { method: "POST" });
      load();
    } catch (e) { setErr(String(e)); }
    setBusy(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Emerging Radar</h1>
        <div className="flex gap-2">
          <select value={window} onChange={(e) => setWindow(Number(e.target.value))} className="border rounded px-2 py-1 text-sm">
            {[7, 14, 30, 60, 90].map((w) => <option key={w} value={w}>{w}-day window</option>)}
          </select>
          <button onClick={runPipeline} disabled={busy} className="rounded bg-slate-900 text-white px-3 py-1 text-sm disabled:opacity-50">
            {busy ? "Running…" : "Snapshot → Aggregate → Score → Graph"}
          </button>
        </div>
      </div>
      <p className="text-xs text-slate-500">Acceleration is derived from ad activity changes between the recent and prior windows. It is NOT a sales signal.</p>
      {err && <p className="text-red-600 text-sm">{err}</p>}
      {!rows && !err && <p>Loading…</p>}
      {rows && rows.length === 0 && <p className="text-slate-500">No emerging products detected. Import more data or run the pipeline above.</p>}
      {rows && rows.length > 0 && (
        <table className="w-full text-sm bg-white shadow rounded">
          <thead className="bg-slate-100 text-left"><tr><th className="p-2">Product</th><th>Acceleration</th><th>Window</th><th>Coverage</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.product_id} className="border-t">
              <td className="p-2"><Link className="text-blue-700 hover:underline" href={`/products/${r.product_id}`}>{r.product_name}</Link></td>
              <td className="p-2 font-semibold">{r.acceleration.toFixed(1)}</td>
              <td className="p-2">{r.window_days}d</td>
              <td className="p-2">{r.coverage_warning ? <span className="text-amber-700" title={r.coverage_warning}>⚠ Low</span> : "OK"}</td>
            </tr>))}
          </tbody>
        </table>
      )}
    </div>
  );
}
