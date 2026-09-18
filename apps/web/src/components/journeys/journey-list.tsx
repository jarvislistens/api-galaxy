"use client";

/**
 * The journey rail.
 *
 * Every row states four things without being asked: how many steps, which services it
 * crosses, where the journey came from, and whether it still validates. The last one is
 * the reason this list exists at all — a journey that no longer validates is the cheapest
 * early warning in the product.
 */

import { AlertTriangle, CheckCircle2, Route, Trash2 } from "lucide-react";
import * as React from "react";
import { Badge, Button, Tooltip, cx } from "@/components/ui/primitives";
import type { Journey } from "@/lib/types";

const SOURCE_LABEL: Record<string, string> = {
  specification: "From specification",
  deterministic_rule: "Derived by rule",
  bundled_analysis: "Bundled analysis",
  ai_inference: "Model inference",
  user_edit: "Yours",
  scenario: "Scenario",
};

const SOURCE_TONE = (kind: string) =>
  kind === "specification" || kind === "deterministic_rule"
    ? ("fact" as const)
    : kind === "user_edit"
      ? ("user" as const)
      : ("inferred" as const);

export function JourneyList({
  journeys,
  selectedId,
  onSelect,
  onDelete,
  deletingId,
}: {
  journeys: Journey[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (journey: Journey) => void;
  deletingId?: string | null;
}) {
  return (
    <ul className="divide-y divide-[var(--color-line)]" aria-label="Journeys">
      {journeys.map((journey) => {
        const active = journey.id === selectedId;
        const validation = journey.validation;
        const broken = validation ? validation.broken_steps.length : 0;
        const ok = validation ? validation.ok : true;
        const kind = journey.provenance.source_kind;
        const userMade = kind === "user_edit";

        return (
          <li key={journey.id} className="relative">
            <button
              onClick={() => onSelect(journey.id)}
              aria-current={active ? "true" : undefined}
              className={cx(
                "block w-full px-3.5 py-3 text-left transition-colors duration-150",
                active
                  ? "bg-[var(--color-surface-3)]"
                  : "hover:bg-[var(--color-surface-2)]",
              )}
            >
              <span className="flex items-start gap-2">
                <Route
                  size={14}
                  aria-hidden
                  className={cx(
                    "mt-[3px] shrink-0",
                    active ? "text-[var(--color-accent-soft)]" : "text-[var(--color-dim)]",
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-[var(--color-ink)]">
                    {journey.name}
                  </span>
                  <span className="numeral mt-0.5 block text-[11.5px] text-[var(--color-dim)]">
                    {journey.steps.length} step{journey.steps.length === 1 ? "" : "s"} ·{" "}
                    {(journey.services ?? []).length} service
                    {(journey.services ?? []).length === 1 ? "" : "s"}
                  </span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {ok ? (
                      <Badge tone="ok" icon={<CheckCircle2 size={11} aria-hidden />}>
                        validates
                      </Badge>
                    ) : (
                      <Badge tone="broken" icon={<AlertTriangle size={11} aria-hidden />}>
                        {broken} step{broken === 1 ? "" : "s"} broken
                      </Badge>
                    )}
                    <Badge tone={SOURCE_TONE(kind)}>{SOURCE_LABEL[kind] ?? kind}</Badge>
                  </span>
                  {(journey.services ?? []).length > 0 && (
                    <span className="mono mt-1.5 block truncate text-[10.5px] text-[var(--color-dim)]">
                      {(journey.services ?? []).join(" → ")}
                    </span>
                  )}
                </span>
              </span>
            </button>

            {userMade && (
              <span className="absolute right-2 top-2.5">
                <Tooltip label="Delete this journey. Only journeys you created can be deleted.">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Delete journey ${journey.name}`}
                    loading={deletingId === journey.id}
                    onClick={() => onDelete(journey)}
                  >
                    <Trash2 size={13} aria-hidden />
                  </Button>
                </Tooltip>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
