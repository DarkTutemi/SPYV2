"use client";
import { useEffect, useState, use } from "react";
import { api, fmt } from "@/lib/api";

type Comp = Record<string, { raw: number; weight: number; description: string }>;
type Report = {
  product: { name: string; description: string | null; image_url: string | null; source_url: string | null; functional_use_case: string | null; us_relevance_confidence: string };
  customer_pain: string | null; us_market_verified: boolean; first_observed: string | null;
  observed_advertiser_count: number; observed_active_ad_count: number; new_ads_7d: number; new_ads_14d: number; new_ads_30d: number;
  ad_persistence_days: number | null; competitor_domains: string[];
  bundle_offers: { id: string; quantity: number; bundle_price_usd: number | null; bundle_mechanism: string; bundle_status: string; source_url: string | null }[];
  emergence_score: number | null; evidence_confidence: number | null; bundle_potential: number | null;
  score_components: { emergence: Comp; confidence: Comp; bundle: Comp } | null;
  momentum_data: { date: string; ads: number }[]; data_gaps: string[];
};
type Ad = { id: string; title: string | null; ad_url: string | null; landing_page_url: string | null; is_active: boolean | null; first_seen_at: string; advertiser_start_date: string | null };

function Components({ title, c }: { title: string; c?: Comp }) {
  if (!c) return null;
  return (
    <div className="bg-white rounded shadow p-3">
      <h3 className="font-semibold mb-2">{title}</h3>
      {Object.entries(c).map(([k, v]) => (
        <div key={k} className="text-xs mb-1" title={v.description}>
          <div className="flex justify-between"><span>{k} (w={v.weight})</span><span>{v.raw.toFixed(1)}</span></div>
          <div className="h-1.5 bg-slate-200 rounded"><div className="h-1.5 bg-slate-700 rounded" style={{ width: `${Math.min(100, v.raw)}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

export default function ProductReport({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [r, setR] = useState<Report | null>(null);
  const [ads, setAds] = useState<Ad[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api<Report>(`/products/${id}/report`).then(setR).catch((e) => setErr(String(e)));
    api<Ad[]>(`/advertisements/?product_id=${id}&page_size=200`).then(setAds).catch(() => {});
  }, [id]);
  if (err) return <p className="text-red-600">{err}</p>;
  if (!r) return <p>Loading…</p>;
  const stat = (label: string, v: unknown) => <div className="bg-white rounded shadow p-3"><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-semibold">{fmt(v)}</div></div>;

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex gap-4">
        {r.product.image_url && <img src={r.product.image_url} alt="" className="w-32 h-32 object-cover rounded bg-slate-200" />}
        <div>
          <h1 className="text-xl font-semibold">{r.product.name}</h1>
          <p className="text-sm text-slate-600 max-w-2xl">{r.product.description ?? "Insufficient evidence"}</p>
          <p className="text-sm mt-1">Use case: {fmt(r.product.functional_use_case)} · Pain: {fmt(r.customer_pain)}</p>
          <p className="text-sm">US relevance: {r.product.us_relevance_confidence} {r.us_market_verified ? "(verified)" : "(not verified)"}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {stat("Emergence", r.emergence_score)}{stat("Evidence confidence", r.evidence_confidence)}{stat("Bundle potential", r.bundle_potential)}
        {stat("Advertisers observed", r.observed_advertiser_count)}{stat("Active ads observed", r.observed_active_ad_count)}
        {stat("First observed (UTC)", r.first_observed?.slice(0, 10))}
        {stat("New ads 7d", r.new_ads_7d)}{stat("New ads 14d", r.new_ads_14d)}{stat("New ads 30d", r.new_ads_30d)}
        {stat("Days since first observed", r.ad_persistence_days)}
      </div>
      <p className="text-xs text-slate-500">“First observed” is when our data first saw it, not the product launch date. Ad counts are not sales.</p>

      <div className="grid md:grid-cols-3 gap-3">
        <Components title="Emergence components" c={r.score_components?.emergence} />
        <Components title="Confidence components" c={r.score_components?.confidence} />
        <Components title="Bundle components" c={r.score_components?.bundle} />
      </div>

      <section className="bg-white rounded shadow p-3">
        <h2 className="font-semibold mb-2">Historical momentum</h2>
        {r.momentum_data.length === 0 ? <p className="text-sm text-slate-500">Insufficient evidence — no daily metrics collected yet.</p> :
          <div className="flex items-end gap-1 h-24">{r.momentum_data.map((m) => <div key={m.date} title={`${m.date}: ${m.ads}`} className="bg-slate-700 w-2" style={{ height: `${Math.min(100, m.ads * 5)}%` }} />)}</div>}
      </section>

      <section className="bg-white rounded shadow p-3">
        <h2 className="font-semibold mb-2">Bundle offers (observed — not proof of purchases)</h2>
        {r.bundle_offers.length === 0 ? <p className="text-sm text-slate-500">No bundle offers observed.</p> :
          <ul className="text-sm">{r.bundle_offers.map((b) => <li key={b.id}>{b.quantity} units · {b.bundle_price_usd != null ? `$${b.bundle_price_usd}` : "price unknown"} · {b.bundle_mechanism} · {b.bundle_status}</li>)}</ul>}
      </section>

      <section className="bg-white rounded shadow p-3">
        <h2 className="font-semibold mb-2">Evidence: advertisements</h2>
        <table className="w-full text-sm"><thead className="text-left"><tr><th>Title</th><th>Active</th><th>Advertiser start</th><th>First seen</th><th>Links</th></tr></thead>
          <tbody>{ads.map((a) => (
            <tr key={a.id} className="border-t"><td>{fmt(a.title)}</td><td>{a.is_active == null ? "Unknown" : a.is_active ? "yes" : "no"}</td>
              <td>{a.advertiser_start_date?.slice(0, 10) ?? "Unknown"}</td><td>{a.first_seen_at.slice(0, 10)}</td>
              <td className="space-x-2">{a.ad_url && <a className="text-blue-700" href={a.ad_url} target="_blank" rel="noreferrer">ad</a>}{a.landing_page_url && <a className="text-blue-700" href={a.landing_page_url} target="_blank" rel="noreferrer">landing</a>}</td></tr>))}
          </tbody></table>
        <p className="text-sm mt-2">Competitor domains: {r.competitor_domains.length ? r.competitor_domains.join(", ") : "Unknown"}</p>
      </section>

      <section className="bg-amber-50 border border-amber-200 rounded p-3">
        <h2 className="font-semibold mb-1">Data gaps</h2>
        {r.data_gaps.length === 0 ? <p className="text-sm">None detected.</p> : <ul className="list-disc pl-5 text-sm">{r.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul>}
      </section>
    </div>
  );
}

