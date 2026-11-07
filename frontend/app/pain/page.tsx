"use client";

import { useEffect, useState } from "react";
import { api, fmt } from "@/lib/api";

type PainCluster = {
  id: string;
  name: string;
  core_problem: string;
  category: string | null;
  distinct_sources: number;
  distinct_authors: number;
  frequency_score: number | null;
  evidence_count: number;
  hypotheses: string[];
  keywords: string[];
  us_confidence: string;
};

type EvidenceItem = {
  id: string;
  language_group: string;
  content: string;
  source_url: string | null;
  source_type: string;
  geographic_context: string;
  sentiment: number;
};

type ClusterDetail = {
  id: string;
  name: string;
  core_problem: string;
  category: string | null;
  frequency_score: number | null;
  recency_score: number | null;
  hypotheses: string[];
  keywords: string[];
  us_confidence: string;
  evidence: EvidenceItem[];
};

type TrendData = {
  keyword: string;
  geo: string;
  data_points: number;
  trajectory: { date: string; interest: number; geo: string }[];
  note: string;
};

export default function PainDiscoveryPage() {
  const [clusters, setClusters] = useState<PainCluster[]>([]);
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [clusterDetail, setClusterDetail] = useState<ClusterDetail | null>(null);
  const [trendKeyword, setTrendKeyword] = useState<string>("");
  const [trendData, setTrendData] = useState<TrendData | null>(null);
  const [loadingTrends, setLoadingTrends] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadClusters = () => {
    setLoading(true);
    api<any[]>("/pain/clusters")
      .then((data) => {
        // Map to format
        const formatted: PainCluster[] = data.map((c) => ({
          id: c.id,
          name: c.name,
          core_problem: c.core_problem,
          category: c.category,
          distinct_sources: c.distinct_source_count,
          distinct_authors: c.distinct_author_count,
          frequency_score: c.frequency_score,
          evidence_count: c.distinct_source_count || 1,
          hypotheses: c.product_hypotheses?.hypotheses || [],
          keywords: c.search_keywords?.keywords || [],
          us_confidence: c.us_relevance_confidence,
        }));
        setClusters(formatted);
        if (formatted.length > 0 && !selectedClusterId) {
          setSelectedClusterId(formatted[0].id);
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadClusters();
  }, []);

  useEffect(() => {
    if (!selectedClusterId) return;
    api<ClusterDetail>(`/pain/clusters/${selectedClusterId}`)
      .then((detail) => {
        setClusterDetail(detail);
        if (detail.keywords.length > 0 && !trendKeyword) {
          setTrendKeyword(detail.keywords[0]);
        }
      })
      .catch((e) => setError(String(e)));
  }, [selectedClusterId]);

  const handleLookupTrends = () => {
    if (!trendKeyword.trim()) return;
    setLoadingTrends(true);
    api<TrendData>(`/pain/trends/${encodeURIComponent(trendKeyword.trim())}`)
      .then(setTrendData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoadingTrends(false));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Engine D — Pain Discovery & Search Trends</h1>
        <p className="text-xs text-slate-500 mt-1">
          Identifies real consumer problems, failed workarounds, and product replacement discussions in the US market.
          <span className="font-semibold text-amber-700 ml-1">
            Discussion volume represents customer frustration, NOT verified purchase demand.
          </span>
        </p>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md">
          {error}
        </div>
      )}

      {/* Main Grid: Clusters List & Detail View */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Clusters List */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-800">
              Identified Pain Clusters ({clusters.length})
            </h2>
            <button
              onClick={loadClusters}
              className="text-xs text-slate-500 hover:text-slate-800 underline"
            >
              Refresh
            </button>
          </div>

          {clusters.length === 0 && !loading && (
            <p className="text-xs text-slate-500">
              No pain clusters imported yet. Import consumer discussions via API.
            </p>
          )}

          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {clusters.map((c) => (
              <div
                key={c.id}
                onClick={() => setSelectedClusterId(c.id)}
                className={`p-3 rounded-md border text-left cursor-pointer transition ${
                  selectedClusterId === c.id
                    ? "bg-indigo-50 border-indigo-300"
                    : "bg-white border-slate-200 hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-sm text-slate-900 truncate">
                    {c.name}
                  </span>
                  <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">
                    Freq: {fmt(c.frequency_score)}
                  </span>
                </div>
                <p className="text-xs text-slate-600 line-clamp-2">{c.core_problem}</p>
                <div className="flex items-center gap-2 mt-2 text-[10px] text-slate-400">
                  <span>US: {c.us_confidence}</span>
                  <span>•</span>
                  <span>{c.distinct_sources} sources</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Selected Cluster Detail & Evidence */}
        <div className="lg:col-span-2 space-y-6">
          {clusterDetail ? (
            <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-5">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-slate-900">{clusterDetail.name}</h2>
                  <span className="text-xs bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded font-medium">
                    US Market ({clusterDetail.us_confidence})
                  </span>
                </div>
                <p className="text-sm text-slate-700 mt-2 bg-slate-50 p-3 rounded border border-slate-100">
                  <span className="font-semibold text-slate-800">Core Problem: </span>
                  {clusterDetail.core_problem}
                </p>
              </div>

              {/* Hypotheses & Keywords */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3 bg-indigo-50/50 border border-indigo-100 rounded-md">
                  <h3 className="text-xs font-bold text-indigo-900 uppercase tracking-wide mb-2">
                    Relevant Product Hypotheses
                  </h3>
                  {clusterDetail.hypotheses.length === 0 ? (
                    <p className="text-xs text-slate-500 italic">No hypotheses attached.</p>
                  ) : (
                    <ul className="list-disc pl-4 text-xs text-slate-700 space-y-1">
                      {clusterDetail.hypotheses.map((h, i) => (
                        <li key={i}>{h}</li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="p-3 bg-slate-50 border border-slate-200 rounded-md">
                  <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide mb-2">
                    Target Search Keywords
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {clusterDetail.keywords.map((kw, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          setTrendKeyword(kw);
                          handleLookupTrends();
                        }}
                        className="text-xs bg-white border border-slate-300 hover:border-indigo-400 text-slate-700 px-2 py-0.5 rounded"
                      >
                        🔍 {kw}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Categorized Evidence Items */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-slate-800">
                  Customer Discussion Evidence ({clusterDetail.evidence.length} excerpts)
                </h3>
                <div className="space-y-2">
                  {clusterDetail.evidence.map((e) => (
                    <div
                      key={e.id}
                      className="p-3 rounded border border-slate-100 bg-slate-50 text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono uppercase font-bold text-[10px] bg-indigo-100 text-indigo-800 px-1.5 py-0.5 rounded">
                          {e.language_group}
                        </span>
                        {e.source_url && (
                          <a
                            href={e.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-blue-600 hover:underline text-[11px]"
                          >
                            Source Link ↗
                          </a>
                        )}
                      </div>
                      <p className="text-slate-800 italic">"{e.content}"</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white p-6 rounded-lg border border-slate-200 text-slate-500 text-sm text-center">
              Select a pain cluster to inspect customer evidence and product hypotheses.
            </div>
          )}

          {/* Google Trends Inspector Card */}
          <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-4">
            <h2 className="text-base font-semibold text-slate-800">
              Google Trends US Interest Verification
            </h2>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={trendKeyword}
                onChange={(e) => setTrendKeyword(e.target.value)}
                placeholder="Enter product keyword..."
                className="border rounded-md px-3 py-1.5 text-sm flex-1 max-w-sm"
              />
              <button
                onClick={handleLookupTrends}
                disabled={loadingTrends}
                className="bg-slate-900 hover:bg-slate-800 text-white text-sm px-4 py-1.5 rounded-md disabled:opacity-50"
              >
                {loadingTrends ? "Querying…" : "Inspect US Trends"}
              </button>
            </div>

            {trendData && (
              <div className="space-y-2 pt-2 border-t">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span>Keyword: <strong>{trendData.keyword}</strong> (Geo: {trendData.geo})</span>
                  <span>{trendData.note}</span>
                </div>
                <div className="flex items-end gap-1.5 h-20 bg-slate-50 p-2 rounded border border-slate-100">
                  {trendData.trajectory.map((point, i) => (
                    <div
                      key={i}
                      title={`${point.date}: Interest ${point.interest}`}
                      className="bg-indigo-600 hover:bg-indigo-700 flex-1 rounded-t transition-all"
                      style={{ height: `${Math.max(10, point.interest)}%` }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
