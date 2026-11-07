"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type Row = { product: { id: string; name: string }; score: { emergence_score: number; evidence_confidence: number; bundle_potential: number; composite_score: number; requires_verification: boolean; verification_reason: string | null } };

export default function Ranking() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api<Row[]>("/products/ranked?page_size=100").then(setRows).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, []);
  const recompute = async () => { setBusy(true); try { await api("/scores/compute", { method: "POST" }); await load(); } catch (e) { setErr(String(e)); } setBusy(false); };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Opportunity Ranking</h1>
        <button onClick={recompute} disabled={busy} className="rounded bg-slate-900 text-white px-3 py-1 text-sm disabled:opacity-50">{busy ? "Scoring…" : "Recompute scores"}</button>
      </div>
      {err && <p className="text-red-600 text-sm">{err}</p>}
      {!rows && !err && <p>Loading…</p>}
      {rows && rows.length === 0 && <p className="text-slate-500">No scored products. Import data, then recompute.</p>}
      {rows && rows.length > 0 && (
        <table className="w-full text-sm bg-white shadow rounded">
          <thead className="bg-slate-100 text-left"><tr>{["Product", "Composite", "Emergence", "Confidence", "Bundle", "Status"].map((h) => <th key={h} className="p-2">{h}</th>)}</tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.product.id} className="border-t">
              <td className="p-2"><Link className="text-blue-700 hover:underline" href={`/products/${r.product.id}`}>{r.product.name}</Link></td>
              <td className="p-2 font-semibold">{fmt(r.score.composite_score)}</td>
              <td className="p-2">{fmt(r.score.emergence_score)}</td>
              <td className="p-2">{fmt(r.score.evidence_confidence)}</td>
              <td className="p-2">{fmt(r.score.bundle_potential)}</td>
              <td className="p-2">{r.score.requires_verification ? <span className="text-amber-700" title={r.score.verification_reason ?? ""}>Needs verification</span> : "—"}</td>
            </tr>))}
          </tbody>
        </table>
      )}
    </div>
  );
}
