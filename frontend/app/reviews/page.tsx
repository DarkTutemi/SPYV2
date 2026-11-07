"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type ReviewItem = {
  id: string;
  product_id: string;
  product_name: string;
  product_image: string | null;
  reviewer: string;
  verdict: "promising" | "rejected" | "needs_more_data" | "testing";
  notes: string | null;
  bundle_assessment: string | null;
  target_aov: number | null;
  target_bundle_qty: number | null;
  action_items: Record<string, any> | null;
  created_at: string;
};

export default function AnalystDecisionsPage() {
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [activeTab, setActiveTab] = useState<string>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReviews = () => {
    setLoading(true);
    const url = activeTab === "all" ? "/reviews/" : `/reviews/?verdict=${activeTab}`;
    api<ReviewItem[]>(url)
      .then(setReviews)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadReviews();
  }, [activeTab]);

  const verdictBadge = (verdict: string) => {
    switch (verdict) {
      case "promising":
        return <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded text-xs font-bold uppercase">Promising</span>;
      case "testing":
        return <span className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs font-bold uppercase">Testing Ads</span>;
      case "needs_more_data":
        return <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded text-xs font-bold uppercase">Needs More Data</span>;
      case "rejected":
        return <span className="bg-rose-100 text-rose-800 px-2 py-0.5 rounded text-xs font-bold uppercase">Rejected</span>;
      default:
        return <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-xs font-bold uppercase">{verdict}</span>;
    }
  };

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Analyst Workflow & Product Decision Queue</h1>
          <p className="text-xs text-slate-500 mt-1">
            Single-operator research decisions: queue promising products for creative testing, log rejection reasons, or monitor watchlists.
          </p>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md">
          {error}
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-2">
        {[
          ["all", "All Decisions"],
          ["promising", "Promising Queue"],
          ["testing", "Currently Testing"],
          ["needs_more_data", "Needs More Data"],
          ["rejected", "Rejected Archive"],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition ${
              activeTab === key
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Reviews List */}
      <div className="space-y-3">
        {reviews.length === 0 && !loading && (
          <div className="bg-white p-8 rounded-lg border border-slate-200 text-center text-slate-500 text-sm">
            No products in this queue yet. Review a product on its Product Intelligence Report page.
          </div>
        )}

        {reviews.map((r) => (
          <div
            key={r.id}
            className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
          >
            <div className="flex items-center gap-3">
              {r.product_image ? (
                <img src={r.product_image} alt="" className="w-16 h-16 object-cover rounded bg-slate-100" />
              ) : (
                <div className="w-16 h-16 rounded bg-slate-100 flex items-center justify-center text-slate-400 text-xs">
                  No Image
                </div>
              )}
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  {verdictBadge(r.verdict)}
                  <Link
                    href={`/products/${r.product_id}`}
                    className="font-bold text-slate-900 hover:text-indigo-600 text-sm"
                  >
                    {r.product_name}
                  </Link>
                </div>
                {r.notes && <p className="text-xs text-slate-600 italic">"{r.notes}"</p>}
                <div className="flex items-center gap-3 text-[11px] text-slate-500">
                  {r.target_aov && <span>Target AOV: <strong>${r.target_aov.toFixed(2)}</strong></span>}
                  {r.target_bundle_qty && <span>Target Bundle: <strong>{r.target_bundle_qty} units</strong></span>}
                  <span>Reviewed: {r.created_at.slice(0, 10)}</span>
                </div>
              </div>
            </div>

            <Link
              href={`/products/${r.product_id}`}
              className="px-3 py-1.5 text-xs font-medium border border-slate-300 rounded hover:bg-slate-50 text-slate-700 shrink-0"
            >
              Open Report ↗
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}

