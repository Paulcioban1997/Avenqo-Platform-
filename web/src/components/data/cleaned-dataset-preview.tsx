"use client";
import { useEffect, useState } from "react";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { DatasetExportMenu } from "@/components/data/dataset-export-menu";

type Preview = { rows: Record<string, unknown>[]; total: number; preview_snapshot?: string };
const cellText = (value: unknown) => value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
export function CleanedDatasetPreview({ datasetId, name, isFr, onClose }: { datasetId: string; name: string; isFr: boolean; onClose: () => void }) {
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    setData(null); setError("");
    apiFetch(`/api/v1/datasets/${datasetId}/rows?limit=100&offset=0`)
      .then(response => response.json())
      .then(value => { if (current) setData(value); })
      .catch(err => { if (current) setError(err instanceof ApiRequestError && err.publicMessage ? err.publicMessage : (isFr ? "Aperçu indisponible." : "Preview unavailable.")); });
    return () => { current = false; };
  }, [datasetId, isFr]);
  const rows = data?.rows ?? [];
  const columns = Array.from(new Set(rows.flatMap(row => Object.keys(row))));
  const downloadImage = () => {
    const escape = (value: string) => value.replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[char]!));
    const width = Math.max(800, columns.length * 220);
    const text = (x: number, y: number, value: string) => `<text x="${x}" y="${y}" font-family="sans-serif" font-size="13">${escape(value)}</text>`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${110 + rows.length * 28}"><rect width="100%" height="100%" fill="white"/>${text(12, 24, name)}${text(12, 48, `${rows.length} / ${data?.total ?? 0} rows — preview; long values truncated`)}${columns.map((c, i) => text(12 + i * 220, 78, c.slice(0, 28))).join("")}${rows.map((row, ri) => columns.map((c, ci) => text(12 + ci * 220, 106 + ri * 28, cellText(row[c]).slice(0, 28))).join("")).join("")}</svg>`;
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = name.replace(/\.[^/.]+$/, "") + "-preview.svg"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div role="dialog" aria-modal="true" aria-label={isFr ? "Aperçu des données nettoyées" : "Cleaned data preview"} className="dataset-preview fixed inset-0 z-50 overflow-auto bg-white p-6 text-slate-900">
    <style>{`@media print { body * { visibility: hidden; } .dataset-preview, .dataset-preview * { visibility: visible; } .dataset-preview { position: absolute; inset: 0; overflow: visible; } .dataset-preview-actions { display: none; } }`}</style>
    <div className="dataset-preview-actions flex flex-wrap gap-4 mb-5">
      <button type="button" onClick={onClose}>{isFr ? "Fermer" : "Close"}</button>
      <button type="button" disabled={!rows.length} onClick={() => window.print()}>{isFr ? "Imprimer / PDF" : "Print / PDF"}</button>
      <button type="button" disabled={!rows.length} onClick={downloadImage}>{isFr ? "Télécharger l’aperçu en image SVG" : "Download preview image (SVG)"}</button>
      <DatasetExportMenu datasetId={datasetId} datasetName={name} isFr={isFr} previewSnapshot={data?.preview_snapshot} previewRowIndices={rows.map((_, i) => i)} onExportError={setError} />
    </div>
    <h2 className="text-xl font-bold">{name}</h2>
    <p className="my-3">{isFr ? "Aperçu : 100 premières lignes au maximum. Les exports nettoyés sont des tableaux ; l’original conserve sa mise en page et ses logos." : "Preview: first 100 rows maximum. Cleaned exports are tables; the original retains its layout and logos."}</p>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>{isFr ? "Chargement…" : "Loading…"}</p>}
    {data && <p>{rows.length} / {data.total} {isFr ? "lignes affichées" : "rows shown"}</p>}
    <table className="mt-4 border-collapse text-sm"><thead><tr>{columns.map(c => <th key={c} className="border border-slate-300 bg-slate-100 p-2 text-left">{c}</th>)}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={i}>{columns.map(c => <td key={c} className="border border-slate-300 p-2 whitespace-pre-wrap">{cellText(row[c])}</td>)}</tr>)}</tbody></table>
  </div>;
}
