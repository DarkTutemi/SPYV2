export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const fmt = (v: unknown) =>
  v === null || v === undefined || v === "" ? "Unknown" : typeof v === "number" ? v.toFixed(1) : String(v);

