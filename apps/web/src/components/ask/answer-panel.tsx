"use client";

/**
 * The answer.
 *
 * Ordered so that the honesty surfaces cannot be skipped: if an answer is ungrounded or
 * carries a warning, that is the first thing on the panel — above the prose, not below a
 * fold. Then the answer, then how sure it is, then what it is standing on. The technical
 * explanation is the only thing that folds away, because it is the only thing that is
 * optional.
 */

import {
  AlertTriangle,
  ChevronRight,
  Clock,
  Database,
  Quote,
  ShieldAlert,
} from "lucide-react";
import * as React from "react";
import {
  Accordion,
  AccordionItem,
  Badge,
  Card,
  SectionTitle,
  cx,
} from "@/components/ui/primitives";
import type { Answer } from "@/lib/types";

function Gauge({ label, value, hint }: { label: string; value: number; hint: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const tone =
    pct >= 75 ? "var(--color-ok)" : pct >= 45 ? "var(--color-degraded)" : "var(--color-broken)";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[12px] text-[var(--color-ink-2)]">{label}</span>
        <span className="numeral text-[13px] font-semibold text-[var(--color-ink)]">{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${pct} percent`}
        className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-3)]"
      >
        <div
          className="h-full rounded-full transition-[width] duration-300 ease-[var(--ease-out-quint)]"
          style={{ width: `${pct}%`, background: tone }}
        />
      </div>
      <p className="mt-1 text-[11px] leading-snug text-[var(--color-dim)]">{hint}</p>
    </div>
  );
}

export function AnswerPanel({
  answer,
  onSelectNode,
}: {
  answer: Answer;
  onSelectNode: (nodeId: string) => void;
}) {
  const { facts, inferences } = answer.fact_vs_inference;
  const cited = facts + inferences;

  return (
    <div className="space-y-4" aria-live="polite" aria-atomic="false">
      {/* ------------------------------------------------- honesty, first ---- */}
      {(!answer.grounded || answer.warning) && (
        <div
          role="alert"
          className={cx(
            "flex items-start gap-2.5 rounded-[var(--radius-md)] border px-3.5 py-3",
            answer.grounded
              ? "border-[color-mix(in_oklab,var(--color-degraded)_42%,transparent)] bg-[color-mix(in_oklab,var(--color-degraded)_10%,transparent)]"
              : "border-[color-mix(in_oklab,var(--color-broken)_42%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_10%,transparent)]",
          )}
        >
          <ShieldAlert
            size={15}
            aria-hidden
            className={cx(
              "mt-[2px] shrink-0",
              answer.grounded ? "text-[var(--color-degraded)]" : "text-[var(--color-broken)]",
            )}
          />
          <div className="min-w-0">
            <p
              className={cx(
                "text-[12.5px] font-semibold",
                answer.grounded ? "text-[var(--color-degraded)]" : "text-[var(--color-broken)]",
              )}
            >
              {answer.grounded ? "Read this before the answer" : "This answer is not grounded"}
            </p>
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
              {answer.warning ||
                "Some of this answer could not be tied back to a node that exists in the graph. Treat it as a suggestion, not a finding."}
            </p>
            {answer.dropped_references.length > 0 && (
              <p className="mono mt-1.5 break-all text-[11px] text-[var(--color-muted)]">
                Discarded invented references: {answer.dropped_references.join(", ")}
              </p>
            )}
          </div>
        </div>
      )}

      {/* --------------------------------------------------------- the answer */}
      <Card className="p-4">
        <p className="label-eyebrow">Answer</p>
        <p className="mt-2 text-[15px] leading-relaxed text-[var(--color-ink)]">{answer.answer}</p>

        {answer.path_labels.length > 0 && (
          <div className="mt-3.5">
            <p className="label-eyebrow mb-1.5">The path it followed</p>
            <ol className="scroll-x flex items-center gap-1 pb-1" aria-label="Answer path">
              {answer.path_labels.map((label, position) => {
                const nodeId = answer.path[position];
                return (
                  <li key={`${label}-${position}`} className="flex shrink-0 items-center gap-1">
                    {position > 0 && (
                      <ChevronRight
                        size={13}
                        className="shrink-0 text-[var(--color-dim)]"
                        aria-hidden
                      />
                    )}
                    <button
                      onClick={() => nodeId && onSelectNode(nodeId)}
                      className="mono whitespace-nowrap rounded-[var(--radius-xs)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2 py-1 text-[11px] text-[var(--color-ink-2)] transition-colors duration-150 hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
                    >
                      {label}
                    </button>
                  </li>
                );
              })}
            </ol>
            <p className="sr-only">
              Path: {answer.path_labels.join(" then ")}
            </p>
          </div>
        )}
      </Card>

      {/* ------------------------------------------- confidence and provenance */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <SectionTitle>How sure it is</SectionTitle>
          <div className="space-y-3">
            <Gauge
              label="Confidence"
              value={answer.confidence}
              hint="How strongly the evidence supports this specific answer."
            />
            <Gauge
              label="Coverage"
              value={answer.coverage}
              hint="How much of the question the graph could actually speak to."
            />
          </div>
        </Card>

        <Card className="p-4">
          <SectionTitle>Fact versus inference</SectionTitle>
          <p className="numeral text-[13px] text-[var(--color-ink)]">
            {cited} cited item{cited === 1 ? "" : "s"}: {facts} specification fact
            {facts === 1 ? "" : "s"}, {inferences} inference{inferences === 1 ? "" : "s"}.
          </p>
          <div className="mt-2.5 flex items-center gap-1.5">
            <Badge tone="fact">{facts} fact{facts === 1 ? "" : "s"}</Badge>
            <Badge tone="inferred">
              {inferences} inference{inferences === 1 ? "" : "s"}
            </Badge>
          </div>
          {cited > 0 && (
            <div
              className="mt-3 flex h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-3)]"
              aria-hidden
            >
              <span
                className="h-full bg-[var(--color-fact)]"
                style={{ width: `${(facts / cited) * 100}%` }}
              />
              <span
                className="h-full bg-[var(--color-inferred)]"
                style={{ width: `${(inferences / cited) * 100}%` }}
              />
            </div>
          )}
          {answer.inference_note && (
            <div className="mt-3 flex items-start gap-2 rounded-[var(--radius-sm)] border border-[color-mix(in_oklab,var(--color-inferred)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-inferred)_10%,transparent)] px-3 py-2">
              <AlertTriangle
                size={13}
                className="mt-[2px] shrink-0 text-[var(--color-inferred)]"
                aria-hidden
              />
              <p className="text-[12px] leading-snug text-[var(--color-ink-2)]">
                {answer.inference_note}
              </p>
            </div>
          )}
        </Card>
      </div>

      {/* -------------------------------------------------------- the evidence */}
      <Card className="p-4">
        <SectionTitle action={
          <span className="numeral text-[11.5px] text-[var(--color-dim)]">
            {answer.evidence.length} item{answer.evidence.length === 1 ? "" : "s"}
          </span>
        }>
          Evidence
        </SectionTitle>
        {answer.evidence.length === 0 ? (
          <p className="text-[12.5px] text-[var(--color-dim)]">
            Nothing in the graph could be cited for this question.
          </p>
        ) : (
          <ul className="space-y-2">
            {answer.evidence.map((item) => (
              <li key={item.node_id}>
                <button
                  onClick={() => onSelectNode(item.node_id)}
                  className="block w-full rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3 py-2.5 text-left transition-colors duration-150 hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-3)]"
                >
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-[12.5px] font-medium text-[var(--color-ink)]">
                      {item.label}
                    </span>
                    <Badge tone={item.is_fact ? "fact" : "inferred"}>
                      {item.is_fact ? "fact" : "inferred"}
                    </Badge>
                    <Badge tone="neutral">{item.type}</Badge>
                    {item.service && (
                      <span className="text-[11px] text-[var(--color-dim)]">{item.service}</span>
                    )}
                  </span>
                  <span className="mt-1 flex items-start gap-1.5 text-[12px] leading-snug text-[var(--color-muted)]">
                    <Quote size={11} className="mt-[3px] shrink-0 text-[var(--color-dim)]" aria-hidden />
                    {item.why}
                  </span>
                  {item.source.length > 0 && (
                    <span className="mono mt-1.5 block break-all text-[11px] text-[var(--color-dim)]">
                      {item.source.join("  ·  ")}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* --------------------------------------------- optional technical read */}
      {answer.technical_explanation && (
        <Card className="px-4 py-1">
          <Accordion type="single" collapsible>
            <AccordionItem value="technical" trigger="Technical explanation">
              <p className="whitespace-pre-line text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
                {answer.technical_explanation}
              </p>
            </AccordionItem>
          </Accordion>
        </Card>
      )}

      {/* ------------------------------------------------------------- footer */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1 text-[11.5px] text-[var(--color-dim)]">
        <span className="flex items-center gap-1.5">
          <Clock size={11} aria-hidden />
          <span className="numeral">{Math.round(answer.latency_ms)} ms</span>
        </span>
        <span>
          {answer.provider} · <span className="mono">{answer.model}</span>
        </span>
        {answer.cached && (
          <span className="flex items-center gap-1.5">
            <Database size={11} aria-hidden /> served from cache
          </span>
        )}
        {typeof answer.input_tokens === "number" && (
          <span className="numeral">{answer.input_tokens} tokens in</span>
        )}
        {typeof answer.output_tokens === "number" && (
          <span className="numeral">{answer.output_tokens} tokens out</span>
        )}
      </div>
    </div>
  );
}
