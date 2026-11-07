"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type Proposal = { product_a_id: string; product_b_id: string; product_b_name: string; match_type: string; similarity: number; confidence: string; relationship: string };
type Cluster = { id: string; name: string; canonical_product_id: string | null; confidence: string; is_reviewed: boolean; member_count: number; members: { product_id: string; relationship: string; similarity: number | null }[] };

export default function ClustersPage() {
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [clusters, setClusters] = useState<Cluster[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const loadClusters = () => { api<Cluster[]>("/clusters/").then(setClusters).catch((e) => setErr(String(e))); };
  useEffect(() => { loadClusters(); }, []);

  const scanProposals = async () => {
    setBusy(true);
    try { setProposals(await api<Proposal[]>("/clusters/proposals")); } catch (e) { setErr(String(e)); }
    setBusy(false);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Product Clusters & Merge Review</h1>
        <button onClick={scanProposals} disabled={busy} className="rounded bg-slate-900 text-white px-3 py-1 text-sm disabled:opacity-50">{busy ? "Scanning…" : "Scan for duplicates"}</button>
      </div>
      <p className="text-xs text-slate-500">Proposals are candidates — they are NOT automatically merged. Review evidence and create clusters manually.</p>
      {err && <p className="text-red-600 text-sm">{err}</p>}

      {proposals && (
        <section className="bg-white rounded shadow p-3">
          <h2 className="font-semibold mb-2">Duplicate proposals ({proposals.length})</h2>
          {proposals.length === 0 ? <p className="text-sm text-slate-500">No duplicates detected.</p> :
            <table className="w-full text-sm"><thead className="text-left"><tr><th className="p-1">Product A</th><th>Product B</th><th>Match</th><th>Similarity</th><th>Confidence</th></tr></thead>
              <tbody>{proposals.map((p, i) => (
                <tr key={i} className="border-t">
                  <td className="p-1"><Link className="text-blue-700 text-xs" href={`/products/${p.product_a_id}`}>{p.product_a_id.slice(0, 8)}…</Link></td>
                  <td className="p-1"><Link className="text-blue-700" href={`/products/${p.product_b_id}`}>{p.product_b_name}</Link></td>
                  <td className="p-1">{p.match_type}</td>
                  <td className="p-1">{(p.similarity * 100).toFixed(0)}%</td>
                  <td className="p-1">{p.confidence}</td>
                </tr>))}
              </tbody></table>}
        </section>
      )}

      <section className="bg-white rounded shadow p-3">
        <h2 className="font-semibold mb-2">Existing clusters</h2>
        {!clusters && <p>Loading…</p>}
        {clusters && clusters.length === 0 && <p className="text-sm text-slate-500">No clusters yet. Scan for duplicates, then create clusters from accepted proposals.</p>}
        {clusters && clusters.length > 0 && clusters.map((c) => (
          <div key={c.id} className="border-b py-2">
            <div className="flex justify-between"><span className="font-medium">{c.name}</span><span className="text-xs text-slate-500">{c.member_count} members · {c.confidence} · {c.is_reviewed ? "reviewed" : "unreviewed"}</span></div>
            <ul className="ml-4 text-xs text-slate-600">{c.members.map((m) => <li key={m.product_id}><Link className="text-blue-700" href={`/products/${m.product_id}`}>{m.product_id.slice(0, 12)}…</Link> ({m.relationship}{m.similarity != null ? `, ${(m.similarity * 100).toFixed(0)}%` : ""})</li>)}</ul>
          </div>
        ))}
      </section>
    </div>
  );
}
