"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type P = { id: string; name: string; category: string | null; min_price_usd: number | null; us_relevance_confidence: string; first_seen_at: string; source_url: string | null };

export default function Products() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<P[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setRows(null);
    api<P[]>(`/products/?page=${page}&page_size=50${q ? `&search=${encodeURIComponent(q)}` : ""}`).then(setRows).catch((e) => setErr(String(e)));
  }, [q, page]);
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Discovery Feed (newest first)</h1>
      <input value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }} placeholder="Search products…" className="border rounded px-2 py-1 w-80" />
      {err && <p className="text-red-600 text-sm">{err}</p>}
      {!rows && !err && <p>Loading…</p>}
      {rows && (
        <table className="w-full text-sm bg-white shadow rounded">
          <thead className="bg-slate-100 text-left"><tr>{["Product", "Category", "Price", "US confidence", "First observed (UTC)", "Source"].map((h) => <th key={h} className="p-2">{h}</th>)}</tr></thead>
          <tbody>{rows.map((p) => (
            <tr key={p.id} className="border-t">
              <td className="p-2"><Link className="text-blue-700 hover:underline" href={`/products/${p.id}`}>{p.name}</Link></td>
              <td className="p-2">{fmt(p.category)}</td>
              <td className="p-2">{p.min_price_usd != null ? `$${p.min_price_usd}` : "Unknown"}</td>
              <td className="p-2">{p.us_relevance_confidence}</td>
              <td className="p-2">{new Date(p.first_seen_at).toISOString().slice(0, 10)}</td>
              <td className="p-2">{p.source_url ? <a className="text-blue-700 hover:underline" href={p.source_url} target="_blank" rel="noreferrer">link</a> : "Unknown"}</td>
            </tr>))}
          </tbody>
        </table>
      )}
      <div className="flex gap-2 text-sm">
        <button disabled={page === 1} onClick={() => setPage(page - 1)} className="border rounded px-2 disabled:opacity-40">Prev</button>
        <span>Page {page}</span>
        <button disabled={!rows || rows.length < 50} onClick={() => setPage(page + 1)} className="border rounded px-2 disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}

