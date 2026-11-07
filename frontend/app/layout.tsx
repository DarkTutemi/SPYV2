import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = { title: "US WIN HUNTER", description: "Evidence-driven US product intelligence" };

const nav = [
  ["/", "Opportunity Ranking"],
  ["/emerging", "Emerging Radar"],
  ["/analytics", "Historical Analytics"],
  ["/alerts", "Alerts & Pipeline"],
  ["/pain", "Pain & Trends"],
  ["/products", "Discovery Feed"],
  ["/clusters", "Product Clusters"],
  ["/advertisers", "Advertiser Explorer"],
  ["/import", "Import Data"],
  ["/health", "Data Health"],
  ["/settings", "Configuration & Weights"],
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 min-h-screen flex">
        <aside className="w-56 shrink-0 bg-slate-900 text-slate-100 p-4 space-y-1">
          <div className="font-bold mb-4">US WIN HUNTER</div>
          {nav.map(([href, label]) => (
            <Link key={href} href={href} className="block rounded px-2 py-1 hover:bg-slate-700 text-sm">{label}</Link>
          ))}
          <p className="text-xs text-slate-400 pt-6">Ad counts are activity signals, not sales. Scores are heuristics.</p>
        </aside>
        <main className="flex-1 p-6 overflow-x-auto">{children}</main>
      </body>
    </html>
  );
}
