"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type P = {
  id: string;
  name: string;
  category: string | null;
  min_price_usd: number | null;
  us_relevance_confidence: string;
  opportunity_status?: string;
  source_type?: string | null;
  primary_bundle_qty?: number | null;
  first_seen_at: string;
  source_url: string | null;
};

export default function Products() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [rows, setRows] = useState<P[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    const searchParam = q ? `&search=${encodeURIComponent(q)}` : "";
    const statusParam = statusFilter !== "ALL" ? `&status=${statusFilter}` : "";
    api<P[]>(`/products/?page=${page}&page_size=50${searchParam}${statusParam}`)
      .then(setRows)
      .catch((e) => setErr(String(e)));
  }, [q, page, statusFilter]);

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "QUALIFIED":
      case "QUALIFIED_OPPORTUNITY":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">QUALIFIED</span>;
      case "SOURCE_VERIFIED":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-900 border border-emerald-400">SOURCE VERIFIED</span>;
      case "UNVERIFIED_IMPORT":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-900 border border-amber-400">UNVERIFIED IMPORT</span>;
      case "RESEARCH_HYPOTHESIS":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-violet-100 text-violet-900 border border-violet-400">RESEARCH HYPOTHESIS</span>;
      case "PARTIALLY_VALIDATED":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-teal-100 text-teal-900 border border-teal-400">PARTIALLY VALIDATED</span>;
      case "NEEDS_VERIFICATION":
      case "NEEDS_SAFETY_VERIFICATION":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">VERIFICATION</span>;
      case "MONITORING":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-300">MONITORING</span>;
      case "REJECTED":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">REJECTED</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">NEW</span>;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-xl font-semibold">Discovery Feed (Newest First)</h1>
          <p className="text-xs text-slate-500 mt-1">All captured commercial advertisements and clustered physical products</p>
        </div>
        <div className="flex items-center gap-3">
          <input
            value={q}
            onChange={(e) => { setPage(1); setQ(e.target.value); }}
            placeholder="Search products…"
            className="border rounded px-3 py-1.5 text-sm w-64 bg-white"
          />
          <select
            value={statusFilter}
            onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }}
            className="border rounded px-2.5 py-1.5 text-sm bg-white"
          >
            <option value="ALL">All Statuses</option>
            <option value="QUALIFIED_OPPORTUNITY">Qualified Opportunities</option>
            <option value="SOURCE_VERIFIED">Source Verified</option>
            <option value="UNVERIFIED_IMPORT">Unverified Import</option>
            <option value="NEEDS_VERIFICATION">Needs Verification</option>
            <option value="MONITORING">Monitoring</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </div>
      </div>

      {err && <p className="text-red-600 text-sm">{err}</p>}
      {!rows && !err && <p className="text-slate-500 py-4">Loading discovered products…</p>}
      {rows && rows.length === 0 && <p className="text-slate-500 py-6">No products found for the selected filter.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto bg-white shadow rounded border">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-left">
              <tr>
                {["Product", "Status", "Bundle Qty", "Category", "Price", "US confidence", "First observed (UTC)", "Source"].map((h) => (
                  <th key={h} className="p-2.5 font-semibold text-slate-700">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="p-2.5 font-medium">
                    <Link className="text-blue-700 hover:underline" href={`/products/${p.id}`}>{p.name}</Link>
                  </td>
                  <td className="p-2.5">{getStatusBadge(p.opportunity_status)}</td>
                  <td className="p-2.5 font-semibold text-slate-600">{p.primary_bundle_qty ? `${p.primary_bundle_qty}-Pack` : "—"}</td>
                  <td className="p-2.5">{fmt(p.category)}</td>
                  <td className="p-2.5">
                    {p.opportunity_status === "UNVERIFIED_IMPORT" || p.source_type === "manual_import" ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-800 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-300" title="Modeled scenario price, unverified external offer">
                        <span className="text-[10px] text-amber-700 font-bold">[Scenario]</span>
                        <span>{p.min_price_usd != null ? `$${p.min_price_usd}` : "Unknown"}</span>
                      </span>
                    ) : p.min_price_usd != null ? (
                      `$${p.min_price_usd}`
                    ) : (
                      <span className="text-slate-400 italic">Unknown</span>
                    )}
                  </td>
                  <td className="p-2.5">{p.us_relevance_confidence}</td>
                  <td className="p-2.5 text-xs text-slate-600">{new Date(p.first_seen_at).toISOString().slice(0, 10)}</td>
                  <td className="p-2.5">
                    {p.source_url ? (
                      <a className="text-blue-700 hover:underline text-xs" href={p.source_url} target="_blank" rel="noreferrer">
                        Source Link
                      </a>
                    ) : "Unknown"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex gap-2 text-sm items-center pt-2">
        <button disabled={page === 1} onClick={() => setPage(page - 1)} className="border rounded px-3 py-1 bg-white disabled:opacity-40">Prev</button>
        <span className="text-xs text-slate-600">Page {page}</span>
        <button disabled={!rows || rows.length < 50} onClick={() => setPage(page + 1)} className="border rounded px-3 py-1 bg-white disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}
