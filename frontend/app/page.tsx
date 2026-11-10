"use client";
import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type Row = {
  product: {
    id: string;
    name: string;
    category?: string | null;
    is_physical?: boolean;
    opportunity_status?: string;
    primary_bundle_qty?: number | null;
    source_url?: string | null;
  };
  score: {
    composite_score: number;
    bundle_potential: number;
    functional_benefit_score?: number;
    discovery_signal_score?: number;
    evidence_confidence: number;
    observed_momentum?: number | null;
    opportunity_status?: string;
    status_reason?: string | null;
    natural_bundle_quantity?: number | null;
    independent_advertisers_count?: number;
    observed_single_price_usd?: number | null;
    observed_bundle_price_usd?: number | null;
    estimated_bundle_scenario?: string | null;
    customer_aov_usd?: number | null;
    emergence_score: number;
    requires_verification: boolean;
    verification_reason: string | null;
  };
};

export default function Ranking() {
  const [activeTab, setActiveTab] = useState<"QUALIFIED" | "ALL">("QUALIFIED");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Filters
  const [selectedBundleQty, setSelectedBundleQty] = useState<string>("ALL");
  const [minConfidence, setMinConfidence] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const loadData = () => {
    const statusParam = activeTab === "QUALIFIED" ? "QUALIFIED_AND_PROMISING" : "ALL";
    let url = `/products/ranked?page_size=100&status=${statusParam}`;
    return api<Row[]>(url)
      .then(setRows)
      .catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    setRows(null);
    loadData();
  }, [activeTab]);

  const recompute = async () => {
    setBusy(true);
    try {
      await api("/scores/compute", { method: "POST" });
      await loadData();
    } catch (e) {
      setErr(String(e));
    }
    setBusy(false);
  };

  // Client-side filtering
  const filteredRows = useMemo(() => {
    if (!rows) return null;
    return rows.filter((r) => {
      // Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        if (!r.product.name.toLowerCase().includes(q)) return false;
      }
      // Bundle Qty
      if (selectedBundleQty !== "ALL") {
        const qty = parseInt(selectedBundleQty, 10);
        if (r.score.natural_bundle_quantity !== qty && r.product.primary_bundle_qty !== qty) {
          return false;
        }
      }
      // Min Confidence
      if (minConfidence > 0 && r.score.evidence_confidence < minConfidence) {
        return false;
      }
      // Sub-status filter on ALL tab
      if (activeTab === "ALL" && statusFilter !== "ALL") {
        const st = r.score.opportunity_status || r.product.opportunity_status;
        if (st !== statusFilter) return false;
      }
      return true;
    });
  }, [rows, searchQuery, selectedBundleQty, minConfidence, statusFilter, activeTab]);

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "QUALIFIED":
      case "QUALIFIED_OPPORTUNITY":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">QUALIFIED</span>;
      case "PROMISING":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-indigo-100 text-indigo-800 border border-indigo-300">PROMISING</span>;
      case "DISCOVERED":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-sky-100 text-sky-800 border border-sky-300">DISCOVERED</span>;
      case "NEEDS_VERIFICATION":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">VERIFICATION</span>;
      case "MONITORING":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-300">MONITORING</span>;
      case "REJECTED":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">REJECTED</span>;
      case "SYNTHETIC_FIXTURE":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-300">SYNTHETIC</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">NEW</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">US WIN HUNTER — Opportunity Ranking</h1>
          <p className="text-sm text-slate-500 mt-1">
            Evidence-driven qualification: US-only physical products with natural 3, 5, 10-unit replenishment & $30–$90 AOV fit.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={recompute}
            disabled={busy}
            className="rounded-md bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 text-sm font-medium shadow transition disabled:opacity-50"
          >
            {busy ? "Scoring Engine Active…" : "Recompute Scores"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center space-x-2 border-b border-slate-200">
        <button
          onClick={() => { setActiveTab("QUALIFIED"); setStatusFilter("ALL"); }}
          className={`px-4 py-2 text-sm font-semibold border-b-2 transition ${
            activeTab === "QUALIFIED"
              ? "border-emerald-600 text-emerald-800 bg-emerald-50/50"
              : "border-transparent text-slate-500 hover:text-slate-700"
          }`}
        >
          QUALIFIED & PROMISING OPPORTUNITIES
          {activeTab === "QUALIFIED" && rows && (
            <span className="ml-2 bg-emerald-200 text-emerald-900 rounded-full px-2 py-0.5 text-xs font-bold">
              {filteredRows?.length ?? rows.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab("ALL")}
          className={`px-4 py-2 text-sm font-semibold border-b-2 transition ${
            activeTab === "ALL"
              ? "border-slate-900 text-slate-900 bg-slate-50"
              : "border-transparent text-slate-500 hover:text-slate-700"
          }`}
        >
          ALL DISCOVERIES
          {activeTab === "ALL" && rows && (
            <span className="ml-2 bg-slate-200 text-slate-800 rounded-full px-2 py-0.5 text-xs font-bold">
              {filteredRows?.length ?? rows.length}
            </span>
          )}
        </button>
      </div>

      {/* Filters Bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 bg-slate-50 p-3 rounded-lg border border-slate-200 text-sm">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Search Products</label>
          <input
            type="text"
            placeholder="Search by name…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Natural Bundle Quantity</label>
          <select
            value={selectedBundleQty}
            onChange={(e) => setSelectedBundleQty(e.target.value)}
            className="w-full bg-white border border-slate-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-500"
          >
            <option value="ALL">All Quantities</option>
            <option value="3">3-Pack (Household Multi-Room)</option>
            <option value="5">5-Pack (Rotation Sweet Spot)</option>
            <option value="10">10-Pack (Deep Replenishment)</option>
          </select>
        </div>

        {activeTab === "ALL" && (
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Status Filter</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full bg-white border border-slate-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="QUALIFIED_OPPORTUNITY">QUALIFIED ONLY</option>
              <option value="NEEDS_VERIFICATION">NEEDS VERIFICATION</option>
              <option value="MONITORING">MONITORING</option>
              <option value="REJECTED">REJECTED (Artificial / Hardware)</option>
            </select>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Min Evidence Confidence: {minConfidence}%</label>
          <input
            type="range"
            min="0"
            max="80"
            step="10"
            value={minConfidence}
            onChange={(e) => setMinConfidence(parseInt(e.target.value, 10))}
            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer mt-2"
          />
        </div>
      </div>

      {err && <div className="p-4 bg-rose-50 border border-rose-200 rounded-md text-rose-700 text-sm">{err}</div>}
      {!rows && !err && <p className="text-slate-500 py-6 text-center">Loading live qualified opportunities…</p>}

      {filteredRows && filteredRows.length === 0 && (
        <div className="text-center py-12 bg-white rounded-lg border border-slate-200 p-8 space-y-2">
          <p className="text-slate-700 font-medium">No products match the selected criteria.</p>
          <p className="text-slate-500 text-xs">Try adjusting your filters or switch to ALL DISCOVERIES tab.</p>
        </div>
      )}

      {/* Table */}
      {filteredRows && filteredRows.length > 0 && (
        <div className="overflow-x-auto bg-white rounded-lg shadow-sm border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-700 border-b border-slate-200 text-left font-semibold">
              <tr>
                <th className="p-3">Rank / Product</th>
                <th className="p-3 text-center">Status</th>
                <th className="p-3 text-right">Composite</th>
                <th className="p-3 text-right" title="Natural Multi-Unit Necessity & $30-$90 AOV fit">Bundle (40%)</th>
                <th className="p-3 text-right" title="Problem clarity & utility mechanics">Functional (30%)</th>
                <th className="p-3 text-right" title="Ad persistence & launch recency">Discovery (20%)</th>
                <th className="p-3 text-right" title="Traceable live URLs & Advertiser proof">Conf (10%)</th>
                <th className="p-3 text-center" title="Target Multi-Unit Offer">Primary Qty</th>
                <th className="p-3 text-center" title="Longitudinal growth acceleration (requires >= 2 collection dates)">Momentum</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRows.map((r, idx) => {
                const status = r.score.opportunity_status || r.product.opportunity_status;
                const isRejected = status === "REJECTED";
                return (
                  <tr key={r.product.id} className={`hover:bg-slate-50/80 transition ${isRejected ? "bg-slate-50/50 opacity-75" : ""}`}>
                    <td className="p-3">
                      <div className="flex items-start gap-2">
                        <span className="font-mono text-xs font-bold text-slate-400 mt-0.5">#{idx + 1}</span>
                        <div>
                          <Link className="font-medium text-blue-700 hover:text-blue-900 hover:underline" href={`/products/${r.product.id}`}>
                            {r.product.name}
                          </Link>
                          {r.score.status_reason && (
                            <p className="text-xs text-slate-500 mt-0.5 line-clamp-1 max-w-xl" title={r.score.status_reason}>
                              {r.score.status_reason}
                            </p>
                          )}
                          <div className="flex flex-wrap items-center gap-1.5 mt-1">
                            {r.score.observed_bundle_price_usd ? (
                              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                                Observed Price: ${r.score.observed_bundle_price_usd.toFixed(2)}
                              </span>
                            ) : r.score.observed_single_price_usd ? (
                              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                                Observed Single: ${r.score.observed_single_price_usd.toFixed(2)}
                              </span>
                            ) : r.score.estimated_bundle_scenario ? (
                              <span className="text-xs text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200" title="Missing observed checkout price in ad creative; modeled based on category heuristics">
                                Scenario: {r.score.estimated_bundle_scenario} (Price Unknown)
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="p-3 text-center whitespace-nowrap">
                      {getStatusBadge(status)}
                    </td>
                    <td className="p-3 text-right font-bold text-slate-900">
                      {fmt(r.score.composite_score)}
                    </td>
                    <td className="p-3 text-right font-medium text-emerald-700">
                      {fmt(r.score.bundle_potential)}
                    </td>
                    <td className="p-3 text-right text-slate-700">
                      {fmt(r.score.functional_benefit_score ?? 0)}
                    </td>
                    <td className="p-3 text-right text-slate-700">
                      {fmt(r.score.discovery_signal_score ?? r.score.emergence_score)}
                    </td>
                    <td className="p-3 text-right text-slate-600">
                      {fmt(r.score.evidence_confidence)}%
                    </td>
                    <td className="p-3 text-center">
                      {(r.score.natural_bundle_quantity || r.product.primary_bundle_qty) ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-slate-100 text-slate-800">
                          {r.score.natural_bundle_quantity || r.product.primary_bundle_qty}-Pack
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="p-3 text-center text-xs">
                      {r.score.observed_momentum != null ? (
                        <span className="font-semibold text-emerald-600">+{fmt(r.score.observed_momentum)}/d</span>
                      ) : (
                        <span className="text-slate-400 italic text-xs" title="Acceleration unobserved: only 1 collection snapshot exists in database">
                          Unobserved
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Research Methodology Footnote */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 text-xs text-slate-600 space-y-2">
        <h3 className="font-semibold text-slate-800">Bundle-First Qualification Methodology</h3>
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Consumable vs Hardware Distinction:</strong> Flat mop hardware handles are single-unit purchases; multi-packs reflect artificial volume discounting and are rejected. Consumable replacement pads and spin heads have natural multi-room and laundry rotation utility.</li>
          <li><strong>Advertiser Independence:</strong> Affiliate network clone domains sharing identical funnel paths are unified and counted as 1 marketing entity.</li>
          <li><strong>Longitudinal Rigor:</strong> Momentum acceleration requires &ge; 2 collection dates. In single-collection runs, momentum is strictly reported as Unobserved.</li>
        </ul>
      </div>
    </div>
  );
}
