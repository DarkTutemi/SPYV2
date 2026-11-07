"use client";

import { useState } from "react";

export default function SettingsPage() {
  const [emergenceWeights] = useState({
    "Independent advertiser acceleration": 0.30,
    "New creative acceleration": 0.25,
    "Ad persistence (sustained investment)": 0.20,
    "Signal recency": 0.15,
    "Non-ad demand confirmation": 0.10,
  });

  const [confidenceWeights] = useState({
    "Temporal data coverage completeness": 0.30,
    "Independent source corroboration": 0.25,
    "Product identity certainty": 0.20,
    "Advertiser independence verification": 0.15,
    "Verifiable evidence links": 0.10,
  });

  const [bundleWeights] = useState({
    "Natural multi-unit necessity": 0.30,
    "Functional benefit of multiple units": 0.25,
    "AOV fit ($30–$90 USD window)": 0.20,
    "Usage frequency / rotation pattern": 0.15,
    "Decision simplicity": 0.10,
  });

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">System Configuration & Scoring Weights</h1>
        <p className="text-xs text-slate-500 mt-1">
          Review engine weights, data source parameters, and LLM classification configuration.
        </p>
      </div>

      {/* Notice */}
      <div className="p-4 bg-indigo-50 border border-indigo-200 text-indigo-900 text-xs rounded-lg space-y-1">
        <p className="font-semibold">Deterministic Scoring Engine Architecture</p>
        <p>
          All opportunity scores are calculated via deterministic heuristics. AI is never used to fabricate scores.
          Each score record snapshots the exact weights used at the moment of computation.
        </p>
      </div>

      {/* Weights Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Emergence */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="border-b pb-2">
            <h2 className="font-bold text-slate-800 text-sm">Emergence Weights (0–100)</h2>
            <p className="text-[11px] text-slate-400">Advertising momentum signal</p>
          </div>
          <div className="space-y-2">
            {Object.entries(emergenceWeights).map(([name, weight]) => (
              <div key={name} className="text-xs flex justify-between items-center">
                <span className="text-slate-600 truncate mr-2">{name}</span>
                <span className="font-mono font-semibold bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">
                  {Math.round(weight * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Confidence */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="border-b pb-2">
            <h2 className="font-bold text-slate-800 text-sm">Evidence Confidence (0–100)</h2>
            <p className="text-[11px] text-slate-400">Data completeness & reliability</p>
          </div>
          <div className="space-y-2">
            {Object.entries(confidenceWeights).map(([name, weight]) => (
              <div key={name} className="text-xs flex justify-between items-center">
                <span className="text-slate-600 truncate mr-2">{name}</span>
                <span className="font-mono font-semibold bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">
                  {Math.round(weight * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Bundle */}
        <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm space-y-3">
          <div className="border-b pb-2">
            <h2 className="font-bold text-slate-800 text-sm">Bundle Potential (0–100)</h2>
            <p className="text-[11px] text-slate-400">Multi-unit & $30–$90 AOV fit</p>
          </div>
          <div className="space-y-2">
            {Object.entries(bundleWeights).map(([name, weight]) => (
              <div key={name} className="text-xs flex justify-between items-center">
                <span className="text-slate-600 truncate mr-2">{name}</span>
                <span className="font-mono font-semibold bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">
                  {Math.round(weight * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Collection & Integration Status */}
      <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-4">
        <h2 className="text-base font-semibold text-slate-800">
          Source Integrations & Access Status
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-100 text-slate-700 font-semibold border-b">
              <tr>
                <th className="py-2 px-3">Integration</th>
                <th className="py-2 px-3">Mode</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Geographic Scope</th>
                <th className="py-2 px-3">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              <tr>
                <td className="py-2.5 px-3 font-semibold text-slate-800">Meta Ad Library</td>
                <td className="py-2.5 px-3 font-mono">Dataset Import / Apify</td>
                <td className="py-2.5 px-3 text-emerald-600 font-medium">Ready</td>
                <td className="py-2.5 px-3">US Only</td>
                <td className="py-2.5 px-3 text-slate-500">Official API excludes US commercial ads; file import active</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-semibold text-slate-800">Google Trends</td>
                <td className="py-2.5 px-3 font-mono">Adapter / Heuristic</td>
                <td className="py-2.5 px-3 text-emerald-600 font-medium">Active</td>
                <td className="py-2.5 px-3">US Only</td>
                <td className="py-2.5 px-3 text-slate-500">Relative search volume trajectory</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-semibold text-slate-800">Reddit Consumer Discussions</td>
                <td className="py-2.5 px-3 font-mono">JSON / CSV Import</td>
                <td className="py-2.5 px-3 text-emerald-600 font-medium">Active</td>
                <td className="py-2.5 px-3">US Only</td>
                <td className="py-2.5 px-3 text-slate-500">Free API is non-commercial only; file import used for compliance</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 font-semibold text-slate-800">AI Mechanism Classification</td>
                <td className="py-2.5 px-3 font-mono">Gemini 2.0 Flash / Heuristics</td>
                <td className="py-2.5 px-3 text-emerald-600 font-medium">Active (Fallback Ready)</td>
                <td className="py-2.5 px-3">US Consumer Context</td>
                <td className="py-2.5 px-3 text-slate-500">Categorizes multi-unit mechanisms and tags as AI_INFERENCE</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

