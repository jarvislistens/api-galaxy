"use client";

/**
 * Findings, in the order the backend ranked them.
 *
 * Two labels do the heavy lifting. Severity says how much it matters; "heuristic" versus
 * "deterministic" says how much you should trust the claim itself. A deterministic
 * finding is a fact about the documents. A heuristic finding is a judgement, and the
 * reader is entitled to know which one they are looking at before they act on it.
 */

import { ArrowUpRight, ShieldAlert, Sparkles, SquareStack } from "lucide-react";
import { Badge, type BadgeTone, Card, SectionTitle } from "@/components/ui/primitives";
import type { Overview, Risk, RiskSeverity } from "@/lib/types";

const SEVERITY: Record<RiskSeverity, { label: string; tone: BadgeTone }> = {
  high: { label: "High", tone: "broken" },
  medium: { label: "Medium", tone: "degraded" },
  low: { label: "Low", tone: "possible" },
  info: { label: "Info", tone: "neutral" },
};

export function RiskList({
  risks,
  ambiguities,
  onOpenNode,
}: {
  risks: Risk[];
  ambiguities: Overview["ambiguities"];
  onOpenNode: (nodeId: string) => void;
}) {
  return (
    <section aria-labelledby="risks-heading">
      <SectionTitle>
        <span id="risks-heading">
          Top risks and ambiguities
          <span className="ml-2 numeral text-[12px] font-normal text-[var(--color-dim)]">
            {risks.length + ambiguities.length}
          </span>
        </span>
      </SectionTitle>
      <p className="-mt-2 mb-3 text-[12.5px] text-[var(--color-muted)]">
        Ranked by severity. Open one to land on the exact node in the galaxy.
      </p>

      <Card className="divide-y divide-[var(--color-line)] overflow-hidden">
        {risks.length === 0 && ambiguities.length === 0 && (
          <p className="px-4 py-6 text-center text-[12.5px] text-[var(--color-dim)]">
            No findings. Every rule ran and none of them fired.
          </p>
        )}

        {risks.map((risk) => {
          const severity = SEVERITY[risk.severity] ?? SEVERITY.info;
          const target = risk.node_ids[0];
          return (
            <button
              key={risk.id}
              type="button"
              disabled={!target}
              onClick={() => target && onOpenNode(target)}
              className="group flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-[var(--color-surface-2)] disabled:cursor-default disabled:hover:bg-transparent"
            >
              <ShieldAlert
                size={15}
                aria-hidden
                className="mt-[3px] shrink-0 text-[var(--color-dim)]"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone={severity.tone}>{severity.label} severity</Badge>
                  <Badge tone={risk.heuristic ? "inferred" : "fact"}>
                    {risk.heuristic ? "Heuristic finding" : "Deterministic finding"}
                  </Badge>
                  <span className="mono text-[11px] text-[var(--color-dim)]">{risk.category}</span>
                </div>
                <h3 className="mt-1.5 text-[13px] font-semibold text-[var(--color-ink)]">
                  {risk.title}
                </h3>
                <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
                  {risk.description}
                </p>
                {risk.recommendation && (
                  <p className="mt-1.5 text-[12px] leading-snug text-[var(--color-ink-2)]">
                    <span className="text-[var(--color-dim)]">What to do · </span>
                    {risk.recommendation}
                  </p>
                )}
                <p className="mt-1.5 text-[11px] text-[var(--color-dim)]">
                  {risk.heuristic
                    ? "A rule judged this. Check it before acting on it."
                    : "Read directly from the documents."}
                  {risk.node_ids.length > 0 && (
                    <>
                      {" · "}
                      <span className="numeral">{risk.node_ids.length}</span> node
                      {risk.node_ids.length === 1 ? "" : "s"} involved
                    </>
                  )}
                </p>
              </div>
              <ArrowUpRight
                size={14}
                aria-hidden
                className="mt-1 shrink-0 text-[var(--color-dim)] transition-colors duration-150 group-hover:text-[var(--color-accent-soft)] group-disabled:opacity-0"
              />
            </button>
          );
        })}

        {ambiguities.map((ambiguity) => {
          const target = ambiguity.node_ids[0];
          return (
            <button
              key={ambiguity.id}
              type="button"
              disabled={!target}
              onClick={() => target && onOpenNode(target)}
              className="group flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-[var(--color-surface-2)] disabled:cursor-default disabled:hover:bg-transparent"
            >
              <SquareStack
                size={15}
                aria-hidden
                className="mt-[3px] shrink-0 text-[var(--color-dim)]"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="inferred" icon={<Sparkles size={11} aria-hidden />}>
                    Ambiguity
                  </Badge>
                  <Badge tone="inferred">Heuristic finding</Badge>
                  <span className="mono text-[11px] text-[var(--color-dim)]">{ambiguity.kind}</span>
                </div>
                <h3 className="mt-1.5 text-[13px] font-semibold text-[var(--color-ink)]">
                  {ambiguity.title}
                </h3>
                <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
                  {ambiguity.description}
                </p>
                <p className="mt-1.5 text-[11px] text-[var(--color-dim)]">
                  Suggested, not stated. <span className="numeral">{ambiguity.node_ids.length}</span>{" "}
                  field{ambiguity.node_ids.length === 1 ? "" : "s"} appear to mean the same thing.
                </p>
              </div>
              <ArrowUpRight
                size={14}
                aria-hidden
                className="mt-1 shrink-0 text-[var(--color-dim)] transition-colors duration-150 group-hover:text-[var(--color-accent-soft)] group-disabled:opacity-0"
              />
            </button>
          );
        })}
      </Card>
    </section>
  );
}
