"use client";

/**
 * About, and the rule catalogue.
 *
 * Every finding the app can raise is listed here with whether it is deterministic or a
 * heuristic. A heuristic that is presented as a fact is the single easiest way for a tool
 * like this to mislead someone, so the distinction is in a column, not a footnote.
 */

import { Info } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Card,
  ErrorState,
  KeyValue,
  LoadingBlock,
  SectionTitle,
} from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";

interface Rule {
  id: string;
  what: string;
  kind: string;
}

export function AboutPanel({
  meta,
  loading,
  error,
  onRetry,
}: {
  meta: any;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const rules: Rule[] = meta?.rules ?? [];

  return (
    <Card className="p-5">
      <SectionTitle>
        <span className="flex items-center gap-1.5">
          <Info size={13} className="text-[var(--color-dim)]" aria-hidden />
          About this build
        </span>
      </SectionTitle>

      {loading ? (
        <LoadingBlock rows={3} label="Loading build information" />
      ) : error ? (
        <ErrorState
          title="Could not read build information"
          detail={error instanceof ApiError ? error.message : String(error)}
          onRetry={onRetry}
        />
      ) : (
        <>
          <dl className="max-w-2xl">
            <KeyValue label="Application">{meta?.app ?? "API Galaxy"}</KeyValue>
            <KeyValue label="Version">
              <span className="mono">{meta?.version ?? "—"}</span>
            </KeyValue>
            <KeyValue label="Data directory">
              <span className="mono break-all">{meta?.data_dir ?? "—"}</span>
            </KeyValue>
            {meta?.limits && (
              <>
                <KeyValue label="Max upload">
                  <span className="numeral">
                    {Math.round((meta.limits.max_upload_bytes ?? 0) / (1024 * 1024))}
                  </span>{" "}
                  MB per file
                </KeyValue>
                <KeyValue label="Max projects">
                  <span className="numeral">{meta.limits.max_projects ?? "—"}</span>
                </KeyValue>
                <KeyValue label="Remote $refs">
                  {meta.limits.allow_remote_refs ? "Resolved" : "Not resolved — network access is off"}
                </KeyValue>
              </>
            )}
          </dl>

          {rules.length > 0 && (
            <div className="mt-5 border-t border-[var(--color-line)] pt-4">
              <p className="label-eyebrow mb-2">
                Rule catalogue — {rules.length} findings this build can raise
              </p>
              <div className="scroll-x">
                <table className="w-full min-w-[640px] border-collapse text-[12.5px]">
                  <caption className="sr-only">
                    Every rule, what it detects, and whether it is deterministic or a heuristic.
                  </caption>
                  <thead>
                    <tr className="border-b border-[var(--color-line)]">
                      <th scope="col" className="px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-dim)]">
                        Rule
                      </th>
                      <th scope="col" className="px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-dim)]">
                        What it detects
                      </th>
                      <th scope="col" className="px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-dim)]">
                        Kind
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule) => (
                      <tr key={rule.id} className="border-b border-[var(--color-line)]">
                        <th scope="row" className="mono px-2.5 py-2 text-left text-[11.5px] font-normal text-[var(--color-ink)]">
                          {rule.id}
                        </th>
                        <td className="px-2.5 py-2 text-[var(--color-muted)]">{rule.what}</td>
                        <td className="px-2.5 py-2">
                          <Badge tone={rule.kind === "deterministic" ? "fact" : "inferred"}>
                            {rule.kind}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[11.5px] leading-snug text-[var(--color-dim)]">
                A deterministic rule is true or false about the document. A heuristic is a
                judgement about naming, shape or convention and can be wrong — it is always
                labelled as inference wherever it appears.
              </p>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
