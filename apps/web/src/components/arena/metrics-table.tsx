"use client";

/**
 * The scoreboard.
 *
 * `hallucinated_references` is the honesty metric — how many nodes a provider referred to
 * that do not exist in the graph — so it gets its own emphasised column rather than being
 * buried at the end of a row of counts. A zero there is the good result and is shown as a
 * zero, not as a blank.
 */

import { AlertOctagon, CheckCircle2, XCircle } from "lucide-react";
import * as React from "react";
import { Badge, Card, SectionTitle, Tooltip, cx } from "@/components/ui/primitives";
import type { ArenaMetrics } from "@/lib/types";

const PROVIDER_LABEL: Record<string, string> = {
  deterministic: "Deterministic",
  ollama: "Ollama (local)",
  kimi: "Kimi (external)",
};

function ms(value: number): string {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function usd(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value === 0) return "$0.00";
  return value < 0.01 ? `<$0.01` : `$${value.toFixed(2)}`;
}

export function MetricsTable({
  metrics,
  disclaimer,
}: {
  metrics: ArenaMetrics[];
  disclaimer?: string;
}) {
  return (
    <Card className="p-5">
      <SectionTitle>Run metrics</SectionTitle>

      <div className="scroll-x">
        <table className="w-full min-w-[1080px] border-collapse text-[12.5px]">
          <caption className="sr-only">
            One row per provider: whether the run succeeded, whether the structured output
            parsed, retries, latency, tokens, estimated cost, what was found, and how many
            references did not exist in the graph.
          </caption>
          <thead>
            <tr className="border-b border-[var(--color-line)]">
              {[
                "Provider",
                "Model",
                "Ran",
                "Valid output",
                "Retries",
                "Latency",
                "In / out tokens",
                "Est. cost",
                "Entities",
                "Relations",
                "Aliases",
                "Domains",
                "Risks",
              ].map((label) => (
                <th
                  key={label}
                  scope="col"
                  className="whitespace-nowrap px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-dim)]"
                >
                  {label}
                </th>
              ))}
              <th
                scope="col"
                className="whitespace-nowrap border-l border-[var(--color-line-strong)] bg-[color-mix(in_oklab,var(--color-broken)_9%,transparent)] px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-broken)]"
              >
                <Tooltip label="References the provider produced that do not exist anywhere in the graph. They are discarded before you see them — this is the count of how often it happened.">
                  <span className="flex cursor-help items-center gap-1">
                    <AlertOctagon size={11} aria-hidden />
                    Hallucinated refs
                  </span>
                </Tooltip>
              </th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((row) => (
              <tr key={`${row.provider}-${row.model}`} className="border-b border-[var(--color-line)]">
                <th scope="row" className="whitespace-nowrap px-2.5 py-2.5 text-left font-medium text-[var(--color-ink)]">
                  {PROVIDER_LABEL[row.provider] ?? row.provider}
                </th>
                <td className="mono whitespace-nowrap px-2.5 py-2.5 text-[11.5px] text-[var(--color-muted)]">
                  {row.model || "—"}
                </td>
                <td className="px-2.5 py-2.5">
                  <span className="flex items-center gap-1.5">
                    {row.ok ? (
                      <CheckCircle2 size={12} className="text-[var(--color-ok)]" aria-hidden />
                    ) : (
                      <XCircle size={12} className="text-[var(--color-broken)]" aria-hidden />
                    )}
                    <span className={row.ok ? "text-[var(--color-ink-2)]" : "text-[var(--color-broken)]"}>
                      {row.ok ? "Yes" : "No"}
                    </span>
                  </span>
                </td>
                <td className="px-2.5 py-2.5">
                  <span className="flex items-center gap-1.5">
                    {row.valid_structured_output ? (
                      <CheckCircle2 size={12} className="text-[var(--color-ok)]" aria-hidden />
                    ) : (
                      <XCircle size={12} className="text-[var(--color-degraded)]" aria-hidden />
                    )}
                    <span className="text-[var(--color-ink-2)]">
                      {row.valid_structured_output ? "Yes" : "No"}
                    </span>
                  </span>
                </td>
                <td className="numeral px-2.5 py-2.5 text-[var(--color-ink-2)]">{row.retries}</td>
                <td className="numeral whitespace-nowrap px-2.5 py-2.5 text-[var(--color-ink-2)]">
                  {ms(row.latency_ms)}
                </td>
                <td className="numeral whitespace-nowrap px-2.5 py-2.5 text-[var(--color-ink-2)]">
                  {row.input_tokens ?? "—"} / {row.output_tokens ?? "—"}
                </td>
                <td className="numeral whitespace-nowrap px-2.5 py-2.5 text-[var(--color-ink-2)]">
                  {usd(row.estimated_cost_usd)}
                </td>
                <td className="numeral px-2.5 py-2.5 text-[var(--color-ink-2)]">{row.entities}</td>
                <td className="numeral px-2.5 py-2.5 text-[var(--color-ink-2)]">{row.relations}</td>
                <td className="numeral px-2.5 py-2.5 text-[var(--color-ink-2)]">{row.aliases}</td>
                <td className="numeral px-2.5 py-2.5 text-[var(--color-ink-2)]">{row.domains}</td>
                <td className="numeral px-2.5 py-2.5 text-[var(--color-ink-2)]">{row.risks}</td>
                <td
                  className={cx(
                    "numeral border-l border-[var(--color-line-strong)] px-2.5 py-2.5 text-[15px] font-semibold",
                    row.hallucinated_references > 0
                      ? "bg-[color-mix(in_oklab,var(--color-broken)_12%,transparent)] text-[var(--color-broken)]"
                      : "bg-[color-mix(in_oklab,var(--color-ok)_8%,transparent)] text-[var(--color-ok)]",
                  )}
                >
                  {row.hallucinated_references}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {metrics.some((row) => !row.ok && row.error) && (
        <ul className="mt-3 space-y-1">
          {metrics
            .filter((row) => !row.ok && row.error)
            .map((row) => (
              <li key={row.provider} className="text-[12px] text-[var(--color-broken)]">
                {PROVIDER_LABEL[row.provider] ?? row.provider}: {row.error}
              </li>
            ))}
        </ul>
      )}

      {metrics.some((row) => row.rationale) && (
        <div className="mt-4 space-y-2 border-t border-[var(--color-line)] pt-3">
          <p className="label-eyebrow">How each provider described the estate</p>
          {metrics
            .filter((row) => row.rationale)
            .map((row) => (
              <p key={row.provider} className="text-[12.5px] leading-snug text-[var(--color-muted)]">
                <Badge tone="neutral" className="mr-1.5">
                  {PROVIDER_LABEL[row.provider] ?? row.provider}
                </Badge>
                {row.rationale}
              </p>
            ))}
        </div>
      )}

      {disclaimer && (
        <p className="mt-3 text-[12px] text-[var(--color-muted)]">{disclaimer}</p>
      )}
    </Card>
  );
}
