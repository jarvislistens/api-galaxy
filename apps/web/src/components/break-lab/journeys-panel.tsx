"use client";

/**
 * What the change does to the business flows.
 *
 * A broken field is abstract; "Register Customer stops at step 2" is not. Every broken step
 * is listed with the backend's own reason string rather than a paraphrase.
 */

import { CheckCircle2, Route, XCircle } from "lucide-react";
import * as React from "react";
import { Badge, Card, EmptyState, SectionTitle, cx } from "@/components/ui/primitives";
import type { JourneyValidation } from "@/lib/types";

export function JourneysPanel({
  affected,
  all,
}: {
  affected: JourneyValidation[];
  all: JourneyValidation[];
}) {
  const [showAll, setShowAll] = React.useState(false);
  const rows = showAll ? all : affected;
  const brokenCount = all.filter((journey) => !journey.ok).length;

  return (
    <Card className="p-5">
      <SectionTitle
        action={
          all.length > affected.length ? (
            <button
              type="button"
              onClick={() => setShowAll((current) => !current)}
              aria-pressed={showAll}
              className="text-[12px] text-[var(--color-accent-soft)] underline-offset-2 hover:underline"
            >
              {showAll ? `Show only the ${affected.length} affected` : `Show all ${all.length}`}
            </button>
          ) : null
        }
      >
        Affected journeys
      </SectionTitle>

      <p className="mb-3 text-[12px] text-[var(--color-muted)]">
        <span className="numeral">{brokenCount}</span> of{" "}
        <span className="numeral">{all.length}</span> journeys stop working under this scenario.
      </p>

      {rows.length === 0 ? (
        <EmptyState
          icon={<Route size={20} aria-hidden />}
          title="No journey is affected"
          body="Every recorded business flow still validates end to end against the changed graph."
        />
      ) : (
        <ul className="space-y-2.5">
          {rows.map((journey) => {
            const broken = new Set(journey.broken_steps);
            const failing = journey.steps.filter((step) => !step.ok);
            return (
              <li
                key={journey.journey_id}
                className={cx(
                  "rounded-[var(--radius-md)] border p-3.5",
                  journey.ok
                    ? "border-[var(--color-line)] bg-[var(--color-surface)]"
                    : "border-[color-mix(in_oklab,var(--color-broken)_32%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_7%,transparent)]",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-2">
                    {journey.ok ? (
                      <CheckCircle2
                        size={14}
                        className="mt-[2px] shrink-0 text-[var(--color-ok)]"
                        aria-hidden
                      />
                    ) : (
                      <XCircle
                        size={14}
                        className="mt-[2px] shrink-0 text-[var(--color-broken)]"
                        aria-hidden
                      />
                    )}
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-[var(--color-ink)]">
                        {journey.journey_name}
                      </p>
                      <p className="mt-0.5 text-[12px] text-[var(--color-muted)]">
                        {journey.summary}
                      </p>
                    </div>
                  </div>
                  <Badge tone={journey.ok ? "ok" : "broken"}>{journey.ok ? "OK" : "Broken"}</Badge>
                </div>

                {failing.length > 0 && (
                  <ul className="mt-3 space-y-2 border-t border-[var(--color-line)] pt-3">
                    {failing.map((step) => (
                      <li key={step.step_id}>
                        <p className="mono text-[11.5px] text-[var(--color-ink-2)]">
                          {step.step_id}
                          {broken.has(step.step_id) ? " · broken" : " · degraded"}
                        </p>
                        <ul className="mt-1 space-y-0.5">
                          {step.reasons.map((reason, index) => (
                            <li
                              key={`${step.step_id}-${index}`}
                              className="text-[12px] leading-snug text-[var(--color-muted)]"
                            >
                              {reason}
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
