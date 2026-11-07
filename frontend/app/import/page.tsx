"use client";
import { useState } from "react";
import { API } from "@/lib/api";

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState("meta_ad_library");
  const [out, setOut] = useState<string>("");
  const submit = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("source_type", type);
    setOut("Importing…");
    try {
      const r = await fetch(`${API}/import/file`, { method: "POST", body: fd });
      setOut(JSON.stringify(await r.json(), null, 2));
    } catch (e) { setOut(String(e)); }
  };
  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold">Import legitimately obtained data</h1>
      <p className="text-sm text-slate-600">Accepts JSON / JSONL / CSV, e.g. Apify Meta Ad Library dataset exports. Each record is stored with provenance; re-importing the same ad IDs is detected as duplicate.</p>
      <select value={type} onChange={(e) => setType(e.target.value)} className="border rounded px-2 py-1">
        <option value="meta_ad_library">Meta Ad Library export (Apify/manual)</option>
        <option value="manual_import">Generic products/advertisers</option>
      </select>
      <input type="file" accept=".json,.jsonl,.csv,.tsv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block" />
      <button onClick={submit} disabled={!file} className="rounded bg-slate-900 text-white px-3 py-1 text-sm disabled:opacity-50">Import</button>
      {out && <pre className="bg-white shadow rounded p-3 text-xs overflow-auto">{out}</pre>}
    </div>
  );
}

