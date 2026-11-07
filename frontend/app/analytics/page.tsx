"use client";

import { useEffect, useState } from "react";
import { api, fmt } from "@/lib/api";

type DailyOverview = {
  date: string;
  total_ads: number;
  total_new_ads: number;
  max_advertisers: number;
  products_tracked: number;
};

type AnalyticsOverview = {
  window_days: number;
  start_date: string;
  end_date: string;
  daily_overview: DailyOverview[];
};

type ProductMetric = {
  date: string;
  active_ads: number;
  new_ads: number;
  unique_advertisers: number;
  new_advertisers: number;
  unique_creatives: number;
  new_creatives: number;
  coverage: number | null;
};

type ProductMetricsResponse = {
  product_id: string;
  product_name: string;
  window_days: number;
  start_date: string;
  end_date: string;
  data_points: number;
  metrics: ProductMetric[];
  coverage_warning: string | null;
};

type ProductOption = {
  id: string;
  name: string;
  target_country: string;
};

export default function HistoricalAnalyticsPage() {
  const [windowDays, setWindowDays] = useState(30);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [productMetrics, setProductMetrics] = useState<ProductMetricsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load products list for dropdown
  useEffect(() => {
    api<ProductOption[]>("/products/?page_size=100")
      .then((data) => {
        setProducts(data);
        if (data.length > 0 && !selectedProductId) {
          setSelectedProductId(data[0].id);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  // Load overview and product metrics on change
  useEffect(() => {
    setLoading(true);
    setError(null);

    Promise.all([
      api<AnalyticsOverview>(`/temporal/analytics/overview?window=${windowDays}`),
      selectedProductId
        ? api<ProductMetricsResponse>(`/temporal/metrics/${selectedProductId}?window=${windowDays}`)
        : Promise.resolve(null),
    ])
      .then(([ov, pm]) => {
        setOverview(ov);
        setProductMetrics(pm);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [windowDays, selectedProductId]);

  return (
    <div className="space-y-6">
      {/* Header & Window Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Historical Advertising Analytics</h1>
          <p className="text-xs text-slate-500 mt-1">
            Persistent daily advertising snapshots over 7 to 90-day windows.
            <span className="font-semibold text-amber-700 ml-1">
              Ad counts indicate marketing activity, not sales volume or revenue.
            </span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-slate-700">Analysis Window:</label>
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="border rounded-md px-3 py-1.5 text-sm bg-white shadow-sm"
          >
            <option value={7}>7 Days</option>
            <option value={14}>14 Days</option>
            <option value={30}>30 Days</option>
            <option value={60}>60 Days</option>
            <option value={90}>90 Days</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md">
          {error}
        </div>
      )}

      {/* Aggregate Overview Card */}
      <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-4">
        <h2 className="text-base font-semibold text-slate-800">
          US Catalog Activity Overview ({windowDays}-Day Window)
        </h2>

        {!overview && loading && <p className="text-sm text-slate-400">Loading aggregate metrics…</p>}

        {overview && overview.daily_overview.length === 0 && (
          <p className="text-sm text-slate-500">
            No daily metrics recorded in this window yet. Run the intelligence pipeline to generate snapshots.
          </p>
        )}

        {overview && overview.daily_overview.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-100 text-slate-700 font-semibold border-b">
                <tr>
                  <th className="py-2 px-3">Date</th>
                  <th className="py-2 px-3">Active Ads (Total)</th>
                  <th className="py-2 px-3">New Ads</th>
                  <th className="py-2 px-3">Max Advertisers</th>
                  <th className="py-2 px-3">Products Tracked</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {overview.daily_overview.map((row) => (
                  <tr key={row.date} className="hover:bg-slate-50">
                    <td className="py-2 px-3 font-mono text-xs text-slate-600">{row.date}</td>
                    <td className="py-2 px-3 font-medium text-slate-900">{row.total_ads}</td>
                    <td className="py-2 px-3 text-emerald-600">+{row.total_new_ads}</td>
                    <td className="py-2 px-3 text-slate-700">{row.max_advertisers}</td>
                    <td className="py-2 px-3 text-slate-500">{row.products_tracked}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Product-Specific Temporal Inspector */}
      <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-base font-semibold text-slate-800">
            Product Deep Dive: Momentum & Daily Activity
          </h2>
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-600">Select Product:</span>
            <select
              value={selectedProductId}
              onChange={(e) => setSelectedProductId(e.target.value)}
              className="border rounded-md px-3 py-1.5 text-sm bg-white shadow-sm max-w-xs truncate"
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {productMetrics?.coverage_warning && (
          <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-md">
            ⚠️ {productMetrics.coverage_warning}
          </div>
        )}

        {!productMetrics && loading && <p className="text-sm text-slate-400">Loading product metrics…</p>}

        {productMetrics && productMetrics.metrics.length === 0 && (
          <p className="text-sm text-slate-500">
            No daily metrics available for this product yet.
          </p>
        )}

        {productMetrics && productMetrics.metrics.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-100 text-slate-700 font-semibold border-b">
                <tr>
                  <th className="py-2 px-3">Date</th>
                  <th className="py-2 px-3">Active Ads</th>
                  <th className="py-2 px-3">New Ads</th>
                  <th className="py-2 px-3">Advertisers</th>
                  <th className="py-2 px-3">New Advertisers</th>
                  <th className="py-2 px-3">Data Coverage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {productMetrics.metrics.map((m) => (
                  <tr key={m.date} className="hover:bg-slate-50">
                    <td className="py-2 px-3 font-mono text-xs text-slate-600">{m.date}</td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-900 w-8">{m.active_ads}</span>
                        <div className="w-24 bg-slate-100 h-2 rounded-full overflow-hidden">
                          <div
                            className="bg-indigo-600 h-full rounded-full"
                            style={{ width: `${Math.min(100, m.active_ads * 10)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="py-2 px-3 text-emerald-600">+{m.new_ads}</td>
                    <td className="py-2 px-3 text-slate-800">{m.unique_advertisers}</td>
                    <td className="py-2 px-3 text-blue-600">
                      {m.new_advertisers > 0 ? `+${m.new_advertisers}` : 0}
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-block px-2 py-0.5 text-xs rounded font-medium ${
                          m.coverage === null || m.coverage === undefined
                            ? "bg-slate-100 text-slate-500"
                            : m.coverage >= 0.7
                            ? "bg-emerald-100 text-emerald-800"
                            : m.coverage >= 0.3
                            ? "bg-amber-100 text-amber-800"
                            : "bg-red-100 text-red-800"
                        }`}
                      >
                        {m.coverage !== null && m.coverage !== undefined
                          ? `${Math.round(m.coverage * 100)}%`
                          : "Unknown"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

