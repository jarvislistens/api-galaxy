"use client";

/**
 * Journeys are the only thing on this page a non-technical reader can act on directly,
 * so they carry their provenance badge on the face of the card rather than behind a
 * tooltip: a journey that a rule guessed is not the same claim as one the specification
 * described.
 */

import { AlertTriangle, ArrowUpRight, Route } from "lucide-react";
import { Badge, type BadgeTone, SectionTitle } from "@/components/ui/primitives";
import type { Overview, SourceKind } from "@/lib/types";

const SOURCE: Record<SourceKind, { label: string; tone: BadgeTone }> = {
  specification: { label: "From the specification", tone: "fact" },
  deterministic_rule: { label: "Derived", tone: "fact" },
  bundled_analysis: { label: "Bundled Demo Analysis", tone: "inferred" },
  ai_inference: { label: "Model suggestion", tone: "inferred" },
  user_edit: { label: "Yours", tone: "user" },
  scenario: { label: "Scenario", tone: "degraded" },
};

export function JourneyCards({
  journeys,
  onOpen,
}: {
  journeys: Overview["journeys"];
  onOpen: (journeyId: string) => void;
}) {
  return (
    <section aria-labelledby="journeys-heading">
      <SectionTitle>
        <span id="journeys-heading">
          Business journeys
          <span className="ml-2 numeral text-[12px] font-normal text-[var(--color-dim)]">
            {journeys.length}
          </span>
        </span>
      </SectionTitle>
      <p className="-mt-2 mb-3 text-[12.5px] text-[var(--color-muted)]">
        A journey is one business flow across several services. Open one to play it step by
        step.
      </p>

      <ul className="grid gap-3 lg:grid-cols-2">
        {journeys.map((journey) => {
          const source = SOURCE[journey.source] ?? SOURCE.deterministic_rule;
          return (
            <li key={journey.id}>
              <button
                type="button"
                onClick={() => onOpen(journey.id)}
                className="group panel h-full w-full p-3.5 text-left transition-[border-color,background] duration-200 ease-[var(--ease-out-quint)] hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-2)]"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="flex min-w-0 items-center gap-2 text-[13.5px] font-semibold text-[var(--color-ink)]">
                    <Route size={14} aria-hidden className="shrink-0 text-[var(--color-ok)]" />
                    <span className="truncate">{journey.name}</span>
                  </h3>
                  <ArrowUpRight
                    size={14}
                    aria-hidden
                    className="mt-0.5 shrink-0 text-[var(--color-dim)] transition-colors duration-150 group-hover:text-[var(--color-accent-soft)]"
                  />
                </div>

                <p className="mt-1.5 line-clamp-3 text-[12px] leading-snug text-[var(--color-muted)]">
                  {journey.description}
                </p>

                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <Badge tone="neutral">
                    <span className="numeral">{journey.steps}</span>&nbsp;steps
                  </Badge>
                  <Badge tone="neutral">
                    <span className="numeral">{journey.services.length}</span>&nbsp;
                    {journey.services.length === 1 ? "service" : "services"}
                  </Badge>
                  <Badge tone={source.tone}>{source.label}</Badge>
                  {journey.has_deprecated_step && (
                    <Badge tone="degraded" icon={<AlertTriangle size={11} aria-hidden />}>
                      Uses a deprecated step
                    </Badge>
                  )}
                </div>

                <p className="mono mt-2 truncate text-[11px] text-[var(--color-dim)]">
                  {journey.services.join(" → ")}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
