"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { api, fmt } from "@/lib/api";

type Row = {
  product: {
    id: string;
    name: string;
    category?: string | null;
    source_type?: string | null;
    is_physical?: boolean;
    opportunity_status?: string;
    primary_bundle_qty?: number | null;
    source_url?: string | null;
    min_price_usd?: number | null;
    max_price_usd?: number | null;
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
    verification_reason?: string | null;
    commercial_model?: string | null;
    core_opportunity_score?: number | null;
    bundle_upside_score?: number | null;
    why_it_ranks_high?: string | null;
    why_it_might_fail?: string | null;
    what_evidence_supports_it?: string | null;
    what_remains_unknown?: string | null;
    next_validation_action?: string | null;
  };
};

type ViewMode = "CATEGORY_A" | "CATEGORY_B" | "CATEGORY_C" | "ALL_DISCOVERIES";

export default function Ranking() {
  const [viewMode, setViewMode] = useState<ViewMode>("CATEGORY_C");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [minConfidence, setMinConfidence] = useState<number>(0);
  const [selectedBundleQty, setSelectedBundleQty] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const loadData = () => {
    // When viewing all discoveries, fetch all; otherwise fetch qualified & promising
    const statusParam = viewMode === "ALL_DISCOVERIES" ? "ALL" : "QUALIFIED_AND_PROMISING";
    const url = `/products/ranked?page_size=100&status=${statusParam}`;
    return api<Row[]>(url)
      .then(setRows)
      .catch((e) => setErr(String(e)));
  };

  useEffect(() => {
    setRows(null);
    loadData();
  }, [viewMode]);

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

  // Client-side filtering by commercial model and search
  const filteredRows = useMemo(() => {
    if (!rows) return null;
    return rows.filter((r) => {
      // 1. View Mode / Category Filtering
      const model = r.score.commercial_model || "MODEL_A_SINGLE_PRODUCT";
      if (viewMode === "CATEGORY_A") {
        if (model !== "MODEL_A_SINGLE_PRODUCT") return false;
      } else if (viewMode === "CATEGORY_B") {
        if (model !== "MODEL_B_NATURAL_MULTI_UNIT" && model !== "MODEL_C_HIGH_AOV_OFFER") {
          return false;
        }
      }
      // CATEGORY_C includes all qualified opportunities

      // 2. Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = r.product.name.toLowerCase().includes(q);
        const matchesCat = (r.product.category || "").toLowerCase().includes(q);
        if (!matchesName && !matchesCat) return false;
      }

      // 3. Bundle Qty
      if (selectedBundleQty !== "ALL") {
        const qty = parseInt(selectedBundleQty, 10);
        if (r.score.natural_bundle_quantity !== qty && r.product.primary_bundle_qty !== qty) {
          return false;
        }
      }

      // 4. Min Confidence
      if (minConfidence > 0 && r.score.evidence_confidence < minConfidence) {
        return false;
      }

      // 5. Status filter on ALL tab
      if (viewMode === "ALL_DISCOVERIES" && statusFilter !== "ALL") {
        const st = r.score.opportunity_status || r.product.opportunity_status;
        if (st !== statusFilter) return false;
      }

      return true;
    });
  }, [rows, viewMode, searchQuery, selectedBundleQty, minConfidence, statusFilter]);

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
      case "NEEDS_SAFETY_VERIFICATION":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">SAFETY CHECK</span>;
      case "MONITORING":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-300">MONITORING</span>;
      case "REJECTED":
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">REJECTED</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">NEW</span>;
    }
  };

  const getSourceBadge = (sourceType?: string | null) => {
    switch (sourceType) {
      case "shopify":
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-emerald-100 text-emerald-800 border border-emerald-200" title="Extracted from live verified Shopify D2C store catalog">
            Shopify D2C
          </span>
        );
      case "amazon":
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-orange-100 text-orange-800 border border-orange-200" title="Cross-referenced against US Amazon live marketplace listing">
            Amazon US
          </span>
        );
      case "google_trends":
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-amber-100 text-amber-800 border border-amber-200" title="Google Trends 90-day search volume discovery">
            Google Trends
          </span>
        );
      case "tiktok_creative_center":
      case "tiktok_shop":
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-rose-100 text-rose-800 border border-rose-200">
            TikTok
          </span>
        );
      case "meta_ad_library":
      default:
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-blue-100 text-blue-800 border border-blue-200" title="Meta Ad Library live advertisement tracking">
            Meta Ad Library
          </span>
        );
    }
  };

  const getModelBadge = (model?: string | null) => {
    switch (model) {
      case "MODEL_A_SINGLE_PRODUCT":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-sky-100 text-sky-800 border border-sky-300" title="Model A: Standalone Single-Item Commercial Opportunity">
            Model A: Single-Product
          </span>
        );
      case "MODEL_B_NATURAL_MULTI_UNIT":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300" title="Model B: Natural Multi-Unit Replenishment or Multi-Location Bundle">
            Model B: Natural Multi-Unit
          </span>
        );
      case "MODEL_C_HIGH_AOV_OFFER":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-purple-100 text-purple-800 border border-purple-300" title="Model C: High-AOV Offer / Consumable Refill Starter Kit ($50+)">
            Model C: High-AOV Offer
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700">
            Standard
          </span>
        );
    }
  };

  const getPriceEvidenceBadge = (r: Row) => {
    const src = r.product.source_type;
    const single = r.score.observed_single_price_usd;
    const bundle = r.score.observed_bundle_price_usd;
    const price = bundle || single;

    if (price) {
      if (src === "shopify") {
        return (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-300">
            <span>${price.toFixed(2)}</span>
            <span className="text-[10px] text-emerald-600 font-normal">[Storefront Variant Listing]</span>
          </span>
        );
      } else if (src === "amazon") {
        return (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-orange-800 bg-orange-50 px-2 py-0.5 rounded border border-orange-300">
            <span>${price.toFixed(2)}</span>
            <span className="text-[10px] text-orange-600 font-normal">[Observed Retail Listing]</span>
          </span>
        );
      } else if (src === "google_trends") {
        return (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-purple-800 bg-purple-50 px-2 py-0.5 rounded border border-purple-300">
            <span>${price.toFixed(2)}</span>
            <span className="text-[10px] text-purple-600 font-normal">[Retail Listing Benchmark]</span>
          </span>
        );
      } else {
        return (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-blue-800 bg-blue-50 px-2 py-0.5 rounded border border-blue-300">
            <span>${price.toFixed(2)}</span>
            <span className="text-[10px] text-blue-600 font-normal">[Advertised Price]</span>
          </span>
        );
      }
    } else if (r.score.estimated_bundle_scenario) {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-300" title="Direct checkout price unobserved in creative; modeled on category unit economics">
          <span className="text-[10px] text-slate-500 font-bold">[Scenario Modeled]</span>
          <span>{r.score.estimated_bundle_scenario}</span>
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center text-xs text-slate-400 italic">
          [Price Unobserved]
        </span>
      );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            US WIN HUNTER — Commercial Intelligence & Opportunity Ranking
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Evidence-driven dropshipping discovery: separating Single-Product margin winners, Natural Multi-Unit bundles, and High-AOV offers.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={recompute}
            disabled={busy}
            className="rounded-md bg-slate-900 hover:bg-slate-800 text-white px-4 py-2 text-sm font-medium shadow transition disabled:opacity-50"
          >
            {busy ? "Balanced Scoring Active…" : "Recompute Scores"}
          </button>
        </div>
      </div>

      {/* Commercial Model Category Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-2">
        <button
          onClick={() => { setViewMode("CATEGORY_A"); setStatusFilter("ALL"); }}
          className={`px-3.5 py-2 text-sm font-bold rounded-t-lg transition border-b-2 ${
            viewMode === "CATEGORY_A"
              ? "border-sky-600 text-sky-900 bg-sky-50"
              : "border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          Category A: Best Single-Product (Model A)
          {rows && viewMode === "CATEGORY_A" && (
            <span className="ml-2 bg-sky-200 text-sky-900 rounded-full px-2 py-0.5 text-xs font-bold">
              {filteredRows?.length ?? 0}
            </span>
          )}
        </button>

        <button
          onClick={() => { setViewMode("CATEGORY_B"); setStatusFilter("ALL"); }}
          className={`px-3.5 py-2 text-sm font-bold rounded-t-lg transition border-b-2 ${
            viewMode === "CATEGORY_B"
              ? "border-emerald-600 text-emerald-900 bg-emerald-50"
              : "border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          Category B: Best Bundle / High-AOV (Models B & C)
          {rows && viewMode === "CATEGORY_B" && (
            <span className="ml-2 bg-emerald-200 text-emerald-900 rounded-full px-2 py-0.5 text-xs font-bold">
              {filteredRows?.length ?? 0}
            </span>
          )}
        </button>

        <button
          onClick={() => { setViewMode("CATEGORY_C"); setStatusFilter("ALL"); }}
          className={`px-3.5 py-2 text-sm font-bold rounded-t-lg transition border-b-2 ${
            viewMode === "CATEGORY_C"
              ? "border-indigo-600 text-indigo-900 bg-indigo-50"
              : "border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          Category C: Best Overall Opportunities
          {rows && viewMode === "CATEGORY_C" && (
            <span className="ml-2 bg-indigo-200 text-indigo-900 rounded-full px-2 py-0.5 text-xs font-bold">
              {filteredRows?.length ?? 0}
            </span>
          )}
        </button>

        <button
          onClick={() => { setViewMode("ALL_DISCOVERIES"); setStatusFilter("ALL"); }}
          className={`px-3.5 py-2 text-sm font-semibold rounded-t-lg transition border-b-2 ${
            viewMode === "ALL_DISCOVERIES"
              ? "border-slate-800 text-slate-900 bg-slate-100"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50"
          }`}
        >
          All Discoveries Feed
          {rows && viewMode === "ALL_DISCOVERIES" && (
            <span className="ml-2 bg-slate-300 text-slate-900 rounded-full px-2 py-0.5 text-xs font-bold">
              {filteredRows?.length ?? 0}
            </span>
          )}
        </button>
      </div>

      {/* Category Strategy Banner */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs text-slate-700 flex flex-col md:flex-row md:items-center justify-between gap-2">
        {viewMode === "CATEGORY_A" && (
          <p>
            <strong className="text-sky-900 font-bold">Category A Strategy: </strong>
            High-utility single-item consumer problems. Ranked primarily on Core Problem Utility (50%) and Functional Benefit (25%) without forcing artificial multi-pack penalties.
          </p>
        )}
        {viewMode === "CATEGORY_B" && (
          <p>
            <strong className="text-emerald-900 font-bold">Category B Strategy: </strong>
            Genuine multi-unit demand (consumable replenishment, multi-room coverage, starter kits with refills). Ranked on Bundle Upside (40%) and $30–$90 AOV fit.
          </p>
        )}
        {viewMode === "CATEGORY_C" && (
          <p>
            <strong className="text-indigo-900 font-bold">Category C Strategy: </strong>
            Authoritative balanced commercial ranking (Weights v4). Harmonizes standalone single-item viability and bundle upside fairly.
          </p>
        )}
        {viewMode === "ALL_DISCOVERIES" && (
          <p>
            <strong className="text-slate-900 font-bold">Full Catalog Feed: </strong>
            All 109 canonical physical products discovered across Meta Ad Library, Shopify D2C, Google Trends, and Amazon US.
          </p>
        )}
      </div>

      {/* Filters Bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 bg-white p-3 rounded-lg border border-slate-200 text-sm shadow-sm">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Search Products or Categories</label>
          <input
            type="text"
            placeholder="Search name, category…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-50 border border-slate-300 rounded px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Natural Bundle Quantity</label>
          <select
            value={selectedBundleQty}
            onChange={(e) => setSelectedBundleQty(e.target.value)}
            className="w-full bg-slate-50 border border-slate-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-500"
          >
            <option value="ALL">All Quantities</option>
            <option value="1">Single Unit / 1-Piece</option>
            <option value="2">2-Pack (Twin / Dual Location)</option>
            <option value="3">3-Pack (Household Multi-Room)</option>
            <option value="4">4-Pack (Furniture / Room Set)</option>
            <option value="6">6-Pack / 6-Refill Starter Kit</option>
            <option value="12">12-Pack (Annual Replenishment)</option>
          </select>
        </div>

        {viewMode === "ALL_DISCOVERIES" && (
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Status Filter</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full bg-slate-50 border border-slate-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="QUALIFIED_OPPORTUNITY">QUALIFIED ONLY</option>
              <option value="PROMISING">PROMISING</option>
              <option value="DISCOVERED">DISCOVERED</option>
              <option value="NEEDS_SAFETY_VERIFICATION">SAFETY CHECK</option>
              <option value="REJECTED">REJECTED</option>
            </select>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Min Evidence Confidence: {minConfidence}%
          </label>
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
      {!rows && !err && <p className="text-slate-500 py-6 text-center">Loading evidence-backed opportunities…</p>}

      {filteredRows && filteredRows.length === 0 && (
        <div className="text-center py-12 bg-white rounded-lg border border-slate-200 p-8 space-y-2">
          <p className="text-slate-700 font-medium">No products match the selected criteria.</p>
          <p className="text-slate-500 text-xs">Try adjusting your filters or switch to Category C / All Discoveries.</p>
        </div>
      )}

      {/* Main Opportunities Table */}
      {filteredRows && filteredRows.length > 0 && (
        <div className="overflow-x-auto bg-white rounded-lg shadow-sm border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-700 border-b border-slate-200 text-left font-semibold">
              <tr>
                <th className="p-3">Rank / Product & Evidence</th>
                <th className="p-3 text-center">Commercial Model</th>
                <th className="p-3 text-center">Status</th>
                <th className="p-3 text-right" title="Balanced Composite Score (Weights v4)">Composite</th>
                <th className="p-3 text-right" title="Core Opportunity (Standalone utility & demand)">Core Opp</th>
                <th className="p-3 text-right" title="Bundle Upside (AOV lift & multi-pack feasibility)">Bundle Upside</th>
                <th className="p-3 text-right" title="Traceable evidence confidence">Confidence</th>
                <th className="p-3 text-center" title="Target commercial quantity">Unit Fit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRows.map((r, idx) => {
                const status = r.score.opportunity_status || r.product.opportunity_status;
                const isRejected = status === "REJECTED";
                const model = r.score.commercial_model;
                return (
                  <tr
                    key={r.product.id}
                    className={`hover:bg-slate-50/80 transition ${isRejected ? "bg-slate-50/50 opacity-75" : ""}`}
                  >
                    <td className="p-3 max-w-md">
                      <div className="flex items-start gap-2.5">
                        <span className="font-mono text-xs font-bold text-slate-400 mt-0.5">#{idx + 1}</span>
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Link
                              className="font-semibold text-blue-700 hover:text-blue-900 hover:underline"
                              href={`/products/${r.product.id}`}
                            >
                              {r.product.name}
                            </Link>
                            {getSourceBadge(r.product.source_type)}
                          </div>

                          {/* Authentic Category & Price Evidence */}
                          <div className="flex flex-wrap items-center gap-2">
                            {r.product.category && (
                              <span className="text-[11px] text-slate-500 font-medium">
                                {r.product.category}
                              </span>
                            )}
                            {getPriceEvidenceBadge(r)}
                          </div>

                          {/* Strategic Commentary / Why It Ranks High */}
                          {r.score.why_it_ranks_high && (
                            <p className="text-[11px] text-slate-600 line-clamp-1" title={r.score.why_it_ranks_high}>
                              <span className="font-semibold text-slate-700">Driver: </span>
                              {r.score.why_it_ranks_high}
                            </p>
                          )}

                          {/* Risk / Failure Factor */}
                          {r.score.why_it_might_fail && (
                            <p className="text-[11px] text-amber-700 line-clamp-1" title={r.score.why_it_might_fail}>
                              <span className="font-semibold text-amber-800">Risk: </span>
                              {r.score.why_it_might_fail}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>

                    <td className="p-3 text-center whitespace-nowrap">
                      {getModelBadge(model)}
                    </td>

                    <td className="p-3 text-center whitespace-nowrap">
                      {getStatusBadge(status)}
                    </td>

                    <td className="p-3 text-right font-bold text-slate-900 text-base">
                      {fmt(r.score.composite_score)}
                    </td>

                    <td className="p-3 text-right font-semibold text-sky-800">
                      {fmt(r.score.core_opportunity_score ?? r.score.functional_benefit_score ?? 0)}
                    </td>

                    <td className="p-3 text-right font-semibold text-emerald-800">
                      {r.score.bundle_upside_score != null ? `+${fmt(r.score.bundle_upside_score)}` : "—"}
                    </td>

                    <td className="p-3 text-right text-slate-600 font-medium">
                      {fmt(r.score.evidence_confidence)}%
                    </td>

                    <td className="p-3 text-center">
                      {(r.score.natural_bundle_quantity || r.product.primary_bundle_qty) ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-slate-100 text-slate-800">
                          {r.score.natural_bundle_quantity || r.product.primary_bundle_qty}-Pack
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs text-slate-500 bg-slate-50">
                          Single Unit
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

      {/* Methodology Footnote */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 text-xs text-slate-600 space-y-2">
        <h3 className="font-semibold text-slate-800">Production Commercial Evidence Taxonomy</h3>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <strong>[Observed Checkout Price]:</strong> Verified price variant directly confirmed from Shopify or live D2C merchant cart/checkout.
          </li>
          <li>
            <strong>[Observed Retail Listing]:</strong> Benchmark live marketplace offer verified on Amazon US.
          </li>
          <li>
            <strong>[Advertised Price]:</strong> Creative ad copy price claim observed in live Meta Ad Library.
          </li>
          <li>
            <strong>[Scenario Modeled]:</strong> Modeled AOV scenario when market ads lack explicit checkout amounts. Never misrepresented as verified transaction pricing.
          </li>
        </ul>
      </div>
    </div>
  );
}
