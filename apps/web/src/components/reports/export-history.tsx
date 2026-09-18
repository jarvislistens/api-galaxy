"use client";

/**
 * Everything this project has produced.
 *
 * Every row is re-downloadable from disk, so an export is a artefact you can come back to
 * rather than a one-shot stream you have to regenerate.
 */

import { Download } from "lucide-react";
import * as React from "react";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingBlock,
  SectionTitle,
} from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { ExportRecord } from "@/lib/types";

export function humanSize(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value >= 100 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

function formatTimestamp(value: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString();
}

export function ExportHistory({
  exports,
  loading,
  error,
  onRetry,
}: {
  exports: ExportRecord[];
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  return (
    <Card className="p-5">
      <SectionTitle>Previously generated</SectionTitle>

      {loading ? (
        <LoadingBlock rows={4} label="Loading export history" />
      ) : error ? (
        <ErrorState
          title="Could not load the export history"
          detail={error instanceof ApiError ? error.message : String(error)}
          correlationId={error instanceof ApiError ? error.correlationId : undefined}
          onRetry={onRetry}
        />
      ) : exports.length === 0 ? (
        <EmptyState
          title="Nothing generated yet"
          body="Reports you produce are written to this machine's data directory and listed here so you can download them again without regenerating."
        />
      ) : (
        <div className="scroll-x max-h-[420px] overflow-y-auto rounded-[var(--radius-md)] border border-[var(--color-line)]">
          <table className="w-full min-w-[760px] border-collapse text-[12.5px]">
            <caption className="sr-only">
              Reports already generated for this project, newest first.
            </caption>
            <thead className="sticky top-0 bg-[var(--color-surface-2)]">
              <tr className="border-b border-[var(--color-line)]">
                {["Filename", "Format", "Scope", "Size", "Created", ""].map((label, index) => (
                  <th
                    key={index}
                    scope="col"
                    className="whitespace-nowrap px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-dim)]"
                  >
                    {label || <span className="sr-only">Download</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {exports.map((record) => (
                <tr key={record.id} className="border-b border-[var(--color-line)]">
                  <th
                    scope="row"
                    className="mono max-w-[300px] truncate px-2.5 py-2 text-left text-[11.5px] font-normal text-[var(--color-ink)]"
                    title={record.filename}
                  >
                    {record.filename}
                  </th>
                  <td className="px-2.5 py-2 text-[var(--color-muted)]">{record.format}</td>
                  <td className="px-2.5 py-2 text-[var(--color-muted)]">{record.scope}</td>
                  <td className="numeral whitespace-nowrap px-2.5 py-2 text-[var(--color-ink-2)]">
                    {humanSize(record.size_bytes)}
                  </td>
                  <td className="numeral whitespace-nowrap px-2.5 py-2 text-[11.5px] text-[var(--color-muted)]">
                    {formatTimestamp(record.created_at)}
                  </td>
                  <td className="px-2.5 py-2 text-right">
                    <a
                      href={record.download_url || api.downloadUrl(record.id)}
                      download={record.filename}
                      className="inline-flex h-7 items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2.5 text-[12px] text-[var(--color-ink)] transition-colors hover:bg-[var(--color-surface-3)]"
                      aria-label={`Download ${record.filename} again`}
                    >
                      <Download size={12} aria-hidden />
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
