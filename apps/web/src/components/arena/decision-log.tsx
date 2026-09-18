"use client";

/**
 * The decision log.
 *
 * Append-only, and labelled as such on the page rather than only in the docs: there is no
 * edit control and no delete control here because the API has neither.
 */

import { Lock } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingBlock,
  SectionTitle,
} from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";

export interface DecisionRecord {
  id: string;
  timestamp: string;
  provider: string;
  model: string;
  prompt_template_version: string;
  task: string;
  action: string;
  subject: string;
  editor: string;
}

export function DecisionLog({
  decisions,
  note,
  loading,
  error,
  onRetry,
}: {
  decisions: DecisionRecord[];
  note?: string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  return (
    <Card className="p-5">
      <SectionTitle
        action={
          <Badge tone="fact" icon={<Lock size={11} aria-hidden />}>
            Append-only · immutable
          </Badge>
        }
      >
        Decision log
      </SectionTitle>

      <p className="mb-3 text-[12.5px] text-[var(--color-muted)]">
        {note ||
          "Every accept, merge, rejection and edit is written here with the provider, the model and the prompt template that produced it. Entries are never edited or removed."}
      </p>

      {loading ? (
        <LoadingBlock rows={4} label="Loading the decision log" />
      ) : error ? (
        <ErrorState
          title="Could not load the decision log"
          detail={error instanceof ApiError ? error.message : String(error)}
          correlationId={error instanceof ApiError ? error.correlationId : undefined}
          onRetry={onRetry}
        />
      ) : decisions.length === 0 ? (
        <EmptyState
          title="Nothing decided yet"
          body="Accept, merge or reject a row above and it will appear here with a timestamp."
        />
      ) : (
        <div className="scroll-x max-h-[420px] overflow-y-auto rounded-[var(--radius-md)] border border-[var(--color-line)]">
          <table className="w-full min-w-[860px] border-collapse text-[12.5px]">
            <caption className="sr-only">
              Append-only log of every decision recorded for this project.
            </caption>
            <thead className="sticky top-0 bg-[var(--color-surface-2)]">
              <tr className="border-b border-[var(--color-line)]">
                {["When", "Task", "Action", "Subject", "Provider", "Model", "Template", "Editor"].map(
                  (label) => (
                    <th
                      key={label}
                      scope="col"
                      className="whitespace-nowrap px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-dim)]"
                    >
                      {label}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {decisions.map((record) => (
                <tr key={record.id} className="border-b border-[var(--color-line)]">
                  <td className="numeral whitespace-nowrap px-2.5 py-2 text-[11.5px] text-[var(--color-muted)]">
                    {formatTimestamp(record.timestamp)}
                  </td>
                  <td className="px-2.5 py-2 text-[var(--color-muted)]">{record.task || "—"}</td>
                  <td className="px-2.5 py-2">
                    <Badge tone={toneFor(record.action)}>{record.action.replace(/_/g, " ")}</Badge>
                  </td>
                  <td className="max-w-[320px] px-2.5 py-2 text-[var(--color-ink-2)]">
                    {record.subject}
                  </td>
                  <td className="px-2.5 py-2 text-[var(--color-muted)]">{record.provider || "—"}</td>
                  <td className="mono px-2.5 py-2 text-[11.5px] text-[var(--color-muted)]">
                    {record.model || "—"}
                  </td>
                  <td className="mono px-2.5 py-2 text-[11.5px] text-[var(--color-dim)]">
                    {record.prompt_template_version || "—"}
                  </td>
                  <td className="px-2.5 py-2 text-[var(--color-muted)]">{record.editor || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function toneFor(action: string) {
  if (action.startsWith("accept") || action === "apply") return "ok" as const;
  if (action === "merge" || action === "edit") return "user" as const;
  if (action.startsWith("reject")) return "broken" as const;
  return "neutral" as const;
}

function formatTimestamp(value: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString();
}
