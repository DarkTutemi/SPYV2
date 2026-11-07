"use client";
import { useEffect, useState } from "react";
import { api, fmt } from "@/lib/api";

type A = { id: string; name: string; facebook_page_id: string | null; domain: string | null; is_verified: boolean; first_seen_at: string; last_seen_at: string };
type D = A & { ad_count: number; active_ad_count: number; product_count: number };

export default function Advertisers() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<A[] | null>(null);
  const [sel, setSel] = useState<D | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<A[]>(`/advertisers/?page_size=200${q ? `&search=${encodeURIComponent(q)}` : ""}`).then(setRows).catch((e) => setErr(String(e))); }, [q]);
  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2 space-y-3">
        <h1 className="text-xl font-semibold">Advertiser Explorer</h1>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search advertisers…" className="border rounded px-2 py-1 w-80" />
        {err && <p className="text-red-600 text-sm">{err}</p>}
        {!rows && !err && <p>Loading…</p>}
        {rows && <table className="w-full text-sm bg-white shadow rounded">
          <thead className="bg-slate-100 text-left"><tr><th className="p-2">Name</th><th>Page ID</th><th>Domain</th><th>Last seen (UTC)</th></tr></thead>
          <tbody>{rows.map((a) => (
            <tr key={a.id} className="border-t cursor-pointer hover:bg-slate-50" onClick={() => api<D>(`/advertisers/${a.id}`).then(setSel)}>
              <td className="p-2">{a.name}</td><td>{fmt(a.facebook_page_id)}</td><td>{fmt(a.domain)}</td><td>{a.last_seen_at.slice(0, 10)}</td></tr>))}
          </tbody></table>}
      </div>
      <div>
        {sel ? <div className="bg-white rounded shadow p-3 text-sm space-y-1 sticky top-4">
          <h2 className="font-semibold">{sel.name}</h2>
          <p>Ads observed: {sel.ad_count} (active: {sel.active_ad_count})</p>
          <p>Distinct products: {sel.product_count}</p>
          <p>Identity verified: {sel.is_verified ? "yes" : "no — Page identity not verified"}</p>
          {sel.facebook_page_id && <a className="text-blue-700" target="_blank" rel="noreferrer" href={`https://www.facebook.com/ads/library/?view_all_page_id=${sel.facebook_page_id}&country=US`}>Open in Meta Ad Library</a>}
        </div> : <p className="text-sm text-slate-500 pt-10">Select an advertiser.</p>}
      </div>
    </div>
  );
}

