"use client";

import { useEffect, useState } from "react";
import { api, fmt } from "@/lib/api";

type AlertItem = {
  id: string;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  description: string;
  entity_type: string;
  entity_id: string;
  entity_name: string | null;
  data: Record<string, any> | null;
  is_read: boolean;
  is_dismissed: boolean;
  created_at: string;
};

type AlertResponse = {
  alerts: AlertItem[];
  unread_count: number;
};

type PipelineHistoryItem = {
  id: string;
  run_type: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  steps_completed: Record<string, any> | null;
  errors: Record<string, any> | null;
  alerts_generated: number;
};

export default function AlertsAndPipelinePage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [history, setHistory] = useState<PipelineHistoryItem[]>([]);
  const [isRunningPipeline, setIsRunningPipeline] = useState(false);
  const [pipelineMessage, setPipelineMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = () => {
    setLoading(true);
    let url = `/alerts/?unread_only=${unreadOnly}`;
    if (severityFilter) url += `&severity=${severityFilter}`;

    Promise.all([
      api<AlertResponse>(url),
      api<PipelineHistoryItem[]>("/alerts/scheduler/history"),
    ])
      .then(([alertRes, histRes]) => {
        setAlerts(alertRes.alerts);
        setUnreadCount(alertRes.unread_count);
        setHistory(histRes);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [unreadOnly, severityFilter]);

  const handleMark = async (alertId: string, action: "read" | "dismiss") => {
    try {
      await api("/alerts/mark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_ids: [alertId], action }),
      });
      loadData();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleRunPipeline = async () => {
    setIsRunningPipeline(true);
    setPipelineMessage(null);
    setError(null);
    try {
      const res = await api<any>("/alerts/scheduler/run", { method: "POST" });
      setPipelineMessage(
        `Pipeline finished (${res.status}) in ${res.elapsed_seconds}s. Alerts generated: ${res.steps?.alerts?.alerts_generated ?? 0}`
      );
      loadData();
    } catch (e) {
      setError(`Pipeline run failed: ${e}`);
    } finally {
      setIsRunningPipeline(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Intelligence Alerts & Automation Pipeline</h1>
          <p className="text-xs text-slate-500 mt-1">
            Automated change detection, anomaly alerts, and daily snapshot execution.
          </p>
        </div>

        <button
          onClick={handleRunPipeline}
          disabled={isRunningPipeline}
          className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-4 py-2 rounded-md text-sm shadow-sm transition disabled:opacity-50"
        >
          {isRunningPipeline ? "Executing Full Pipeline…" : "▶ Trigger Pipeline Now"}
        </button>
      </div>

      {pipelineMessage && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-md">
          {pipelineMessage}
        </div>
      )}

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md">
          {error}
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
              className="rounded text-indigo-600"
            />
            Unread Only ({unreadCount})
          </label>

          <span className="text-slate-300">|</span>

          <label className="text-sm font-medium text-slate-700">Severity:</label>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="border rounded-md px-2.5 py-1 text-sm bg-white"
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
        </div>

        <button
          onClick={loadData}
          className="text-xs text-slate-500 hover:text-slate-800 underline"
        >
          Refresh Data
        </button>
      </div>

      {/* Alerts Grid */}
      <div className="space-y-3">
        <h2 className="text-base font-semibold text-slate-800">
          Active Alerts ({alerts.length})
        </h2>

        {alerts.length === 0 && !loading && (
          <div className="bg-white p-6 rounded-lg border border-slate-200 text-center text-slate-500 text-sm">
            No alerts matching your criteria.
          </div>
        )}

        {alerts.map((a) => (
          <div
            key={a.id}
            className={`p-4 rounded-lg border shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4 transition ${
              a.severity === "critical"
                ? "bg-red-50/50 border-red-200"
                : a.severity === "warning"
                ? "bg-amber-50/50 border-amber-200"
                : "bg-white border-slate-200"
            } ${!a.is_read ? "border-l-4 border-l-indigo-600" : ""}`}
          >
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className={`text-xs uppercase font-bold px-2 py-0.5 rounded ${
                    a.severity === "critical"
                      ? "bg-red-100 text-red-800"
                      : a.severity === "warning"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {a.severity}
                </span>
                <span className="text-xs font-mono text-slate-400">
                  {a.alert_type}
                </span>
                <h3 className="font-semibold text-slate-900 text-sm">{a.title}</h3>
              </div>

              <p className="text-xs text-slate-600">{a.description}</p>

              <div className="flex items-center gap-3 text-[11px] text-slate-400">
                <span>Target: {a.entity_name || a.entity_id}</span>
                <span>•</span>
                <span>Time: {a.created_at}</span>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {!a.is_read && (
                <button
                  onClick={() => handleMark(a.id, "read")}
                  className="px-2.5 py-1 text-xs font-medium border border-slate-300 rounded bg-white hover:bg-slate-50 text-slate-700"
                >
                  Mark Read
                </button>
              )}
              <button
                onClick={() => handleMark(a.id, "dismiss")}
                className="px-2.5 py-1 text-xs font-medium border border-transparent rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100"
              >
                Dismiss
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Pipeline Execution History */}
      <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-4">
        <h2 className="text-base font-semibold text-slate-800">
          Automated Pipeline Run History
        </h2>

        {history.length === 0 ? (
          <p className="text-sm text-slate-500">No previous runs recorded.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-100 text-slate-700 font-semibold border-b">
                <tr>
                  <th className="py-2 px-3">Type</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Started At</th>
                  <th className="py-2 px-3">Completed At</th>
                  <th className="py-2 px-3">Alerts Generated</th>
                  <th className="py-2 px-3">Steps Completed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {history.map((h) => (
                  <tr key={h.id} className="hover:bg-slate-50">
                    <td className="py-2 px-3 font-mono text-xs">{h.run_type}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-block px-2 py-0.5 text-xs rounded font-medium ${
                          h.status === "completed"
                            ? "bg-emerald-100 text-emerald-800"
                            : h.status === "running"
                            ? "bg-blue-100 text-blue-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {h.status}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-slate-600">{h.started_at}</td>
                    <td className="py-2 px-3 text-xs text-slate-600">{h.completed_at || "—"}</td>
                    <td className="py-2 px-3 font-semibold text-slate-800">
                      {h.alerts_generated}
                    </td>
                    <td className="py-2 px-3 text-xs font-mono text-slate-500">
                      {h.steps_completed ? Object.keys(h.steps_completed).join(", ") : "—"}
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
