"use client";

/**
 * The first thing anybody sees: how big is this estate, and how much of it is actually
 * stated rather than suggested.
 *
 * The relationship pair is deliberately separated from the object counts by a rule. An
 * inferred relationship is not the same kind of thing as a service — it is a proposal —
 * and putting the two in one undifferentiated row would quietly imply otherwise.
 */

import { Card, cx } from "@/components/ui/primitives";

interface Tile {
  key: string;
  label: string;
  hint: string;
}

const TILES: Tile[] = [
  { key: "services", label: "Services", hint: "One per specification document" },
  { key: "operations", label: "Operations", hint: "Method plus path" },
  { key: "schemas", label: "Schemas", hint: "Named request and response shapes" },
  { key: "fields", label: "Fields", hint: "Leaf properties across every schema" },
  { key: "domains", label: "Domains", hint: "Business areas the services group into" },
  { key: "journeys", label: "Journeys", hint: "Business flows across services" },
  { key: "risks", label: "Findings", hint: "Rule hits worth a look" },
];

function fmt(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString();
}

export function CountsStrip({ counts }: { counts: Record<string, number> }) {
  return (
    <Card className="overflow-hidden">
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7">
        {TILES.map((tile, index) => (
          <div
            key={tile.key}
            className={cx(
              "border-[var(--color-line)] px-4 py-3.5",
              index % 2 === 1 ? "border-l" : "",
              "sm:border-l sm:first:border-l-0",
              "xl:border-l xl:first:border-l-0",
              index >= 2 ? "border-t sm:border-t-0" : "",
              index >= 4 ? "sm:border-t xl:border-t-0" : "",
            )}
          >
            <p className="numeral text-[24px] font-semibold leading-none text-[var(--color-ink)]">
              {fmt(counts[tile.key])}
            </p>
            <p className="mt-1.5 text-[12.5px] font-medium text-[var(--color-ink-2)]">
              {tile.label}
            </p>
            <p className="mt-0.5 text-[11px] leading-tight text-[var(--color-dim)]">{tile.hint}</p>
          </div>
        ))}
      </div>

      {/* The rule below is the point of this component. */}
      <div className="border-t border-[var(--color-line)] bg-[var(--color-surface-2)]/40">
        <div className="grid gap-px sm:grid-cols-2">
          <div className="px-4 py-3.5">
            <div className="flex items-baseline gap-2">
              <span className="numeral text-[22px] font-semibold leading-none text-[var(--color-fact)]">
                {fmt(counts.observed_relationships)}
              </span>
              <span className="text-[12.5px] font-medium text-[var(--color-ink-2)]">
                observed relationships
              </span>
            </div>
            <p className="mt-1 flex items-center gap-2 text-[11.5px] leading-tight text-[var(--color-dim)]">
              <Line stroke="solid" colour="var(--color-fact)" />
              Stated by a document. Drawn solid.
            </p>
          </div>

          <div className="border-t border-[var(--color-line)] px-4 py-3.5 sm:border-l sm:border-t-0">
            <div className="flex items-baseline gap-2">
              <span className="numeral text-[22px] font-semibold leading-none text-[var(--color-inferred)]">
                {fmt(counts.inferred_relationships)}
              </span>
              <span className="text-[12.5px] font-medium text-[var(--color-ink-2)]">
                inferred relationships
              </span>
            </div>
            <p className="mt-1 flex items-center gap-2 text-[11.5px] leading-tight text-[var(--color-dim)]">
              <Line stroke="dashed" colour="var(--color-inferred)" />
              Suggested, not stated. Drawn dashed — accept, edit or reject each one.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

function Line({ stroke, colour }: { stroke: "solid" | "dashed"; colour: string }) {
  return (
    <svg width="22" height="6" viewBox="0 0 22 6" className="shrink-0" aria-hidden>
      <line
        x1="1"
        y1="3"
        x2="21"
        y2="3"
        stroke={colour}
        strokeWidth="1.6"
        strokeDasharray={stroke === "dashed" ? "4 3" : undefined}
      />
    </svg>
  );
}
