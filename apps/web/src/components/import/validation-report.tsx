"use client";

/**
 * What one specification actually is, before anything is imported.
 *
 * The whole point of this component is the failure case: when a document will not parse,
 * the reader should be able to open their editor and go straight to the character that
 * broke it. So line, column and JSON Pointer are shown as prominently as the title.
 */

import { AlertTriangle, CheckCircle2, FileWarning, Info, XCircle } from "lucide-react";
import * as React from "react";
import { Badge, Button, InfoNote, cx } from "@/components/ui/primitives";
import type { ValidationResult } from "@/lib/types";

const COUNT_LABEL: Record<string, string> = {
  operations: "operations",
  schemas: "schemas",
  fields: "fields",
  security_schemes: "security schemes",
};

const KIND_LABEL: Record<string, string> = {
  openapi: "OpenAPI",
  postman: "Postman collection",
  unknown: "Unrecognised",
};

export function ValidationReport({
  filename,
  result,
  pending,
  failure,
  onRemove,
  compact,
}: {
  filename: string;
  result: ValidationResult | null;
  /** True while the validate call is still in flight. */
  pending?: boolean;
  /** A transport-level failure (the validate call itself did not complete). */
  failure?: string | null;
  onRemove?: () => void;
  compact?: boolean;
}) {
  const valid = Boolean(result?.valid);
  const errors = (result?.diagnostics ?? []).filter((d) => d.level === "error");
  const warnings = (result?.diagnostics ?? []).filter((d) => d.level === "warning");
  const infos = (result?.diagnostics ?? []).filter((d) => d.level === "info");

  return (
    <li
      className={cx(
        "rounded-[var(--radius-md)] border p-3.5",
        pending && "border-[var(--color-line)] bg-[var(--color-surface)]",
        !pending && valid && "border-[var(--color-line)] bg-[var(--color-surface)]",
        !pending &&
          !valid &&
          "border-[color-mix(in_oklab,var(--color-broken)_36%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_8%,transparent)]",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className="mt-[2px] shrink-0" aria-hidden>
            {pending ? (
              <Info size={15} className="text-[var(--color-dim)]" />
            ) : valid ? (
              <CheckCircle2 size={15} className="text-[var(--color-ok)]" />
            ) : (
              <XCircle size={15} className="text-[var(--color-broken)]" />
            )}
          </span>
          <div className="min-w-0">
            <p className="mono truncate text-[12.5px] text-[var(--color-ink)]">{filename}</p>
            <p className="mt-0.5 text-[12px] text-[var(--color-muted)]">
              {pending
                ? "Checking…"
                : failure
                  ? failure
                  : valid
                    ? [
                        result?.title || "Untitled document",
                        result?.version ? `v${result.version}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")
                    : "Will not parse — nothing was imported."}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {!pending && result && (
            <Badge tone={valid ? "ok" : "broken"}>
              {valid ? "Valid" : "Invalid"}
            </Badge>
          )}
          {!pending && result?.kind && result.kind !== "unknown" && (
            <Badge tone="neutral">{KIND_LABEL[result.kind] ?? result.kind}</Badge>
          )}
          {onRemove && (
            <Button variant="ghost" size="sm" onClick={onRemove} aria-label={`Remove ${filename}`}>
              Remove
            </Button>
          )}
        </div>
      </div>

      {/* --------------------------------------------------------------- counts */}
      {valid && result && Object.keys(result.counts ?? {}).length > 0 && (
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
          {Object.entries(result.counts).map(([key, value]) => (
            <div key={key} className="flex items-baseline gap-1.5">
              <dd className="numeral text-[14px] font-semibold text-[var(--color-ink)]">{value}</dd>
              <dt className="text-[11.5px] text-[var(--color-dim)]">
                {COUNT_LABEL[key] ?? key.replace(/_/g, " ")}
              </dt>
            </div>
          ))}
        </dl>
      )}

      {/* ------------------------------------------------------ the parse error */}
      {result?.error && (
        <div className="mt-3 rounded-[var(--radius-sm)] border border-[color-mix(in_oklab,var(--color-broken)_34%,transparent)] bg-[var(--color-base)] p-3">
          <p className="text-[12.5px] font-medium text-[var(--color-broken)]">
            {result.error.message}
          </p>
          <div className="mono mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[var(--color-ink-2)]">
            {result.error.line != null && (
              <span>
                line <span className="numeral text-[var(--color-ink)]">{result.error.line}</span>
              </span>
            )}
            {result.error.column != null && (
              <span>
                column{" "}
                <span className="numeral text-[var(--color-ink)]">{result.error.column}</span>
              </span>
            )}
            {result.error.field_path && (
              <span>
                at <span className="text-[var(--color-ink)]">{result.error.field_path}</span>
              </span>
            )}
          </div>
          {result.error.hint && (
            <p className="mt-2 text-[12px] leading-snug text-[var(--color-muted)]">
              {result.error.hint}
            </p>
          )}
        </div>
      )}

      {/* --------------------------------------------------------- diagnostics */}
      {!compact && (errors.length > 0 || warnings.length > 0 || infos.length > 0) && (
        <ul className="mt-3 space-y-1.5">
          {[...errors, ...warnings, ...infos].slice(0, 12).map((d, index) => (
            <li key={`${d.code}-${index}`} className="flex items-start gap-2 text-[12px]">
              {d.level === "error" ? (
                <XCircle size={12} className="mt-[3px] shrink-0 text-[var(--color-broken)]" aria-hidden />
              ) : d.level === "warning" ? (
                <AlertTriangle
                  size={12}
                  className="mt-[3px] shrink-0 text-[var(--color-degraded)]"
                  aria-hidden
                />
              ) : (
                <Info size={12} className="mt-[3px] shrink-0 text-[var(--color-dim)]" aria-hidden />
              )}
              <span className="min-w-0">
                <span className="text-[var(--color-ink-2)]">{d.message}</span>{" "}
                <span className="mono text-[11px] text-[var(--color-dim)]">
                  {[d.file, d.pointer].filter(Boolean).join(" ")}
                  {d.level !== "error" ? ` · ${d.level}` : ""}
                </span>
                {d.hint && (
                  <span className="mt-0.5 block text-[11.5px] text-[var(--color-muted)]">
                    {d.hint}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* ------------------------------------------------------------- preview */}
      {!compact && valid && result?.preview && result.preview.operations.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[12px] text-[var(--color-muted)] hover:text-[var(--color-ink)]">
            Preview {result.preview.operations.length} operation
            {result.preview.operations.length === 1 ? "" : "s"}
          </summary>
          <ul className="mono mt-2 max-h-48 space-y-1 overflow-y-auto pr-1 text-[11.5px]">
            {result.preview.operations.map((op) => (
              <li key={op.id} className="flex items-baseline gap-2">
                <span className="w-[52px] shrink-0 text-right text-[var(--color-accent-soft)]">
                  {op.method}
                </span>
                <span className="min-w-0 truncate text-[var(--color-ink-2)]">{op.path}</span>
                {op.deprecated && <Badge tone="degraded">deprecated</Badge>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {valid && result?.kind === "postman" && (
        <div className="mt-3">
          <InfoNote>
            A Postman collection records requests, not a schema. Paths, methods and names are
            recovered; request and response bodies, field types and relationships are not.
          </InfoNote>
        </div>
      )}

      {failure && !result && (
        <p className="mt-3 flex items-start gap-2 text-[12px] text-[var(--color-broken)]">
          <FileWarning size={13} className="mt-[2px] shrink-0" aria-hidden />
          {failure}
        </p>
      )}
    </li>
  );
}
