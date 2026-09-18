"use client";

/**
 * Before and after, side by side.
 *
 * Deltas are shown with a sign and a word, never a bare coloured number, and a delta of
 * zero is written as "no change" rather than left blank — blank reads as "not measured".
 */

import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import * as React from "react";
import { Card, EmptyState, SectionTitle, cx } from "@/components/ui/primitives";
import type { JourneyValidation } from "@/lib/types";

interface Side {
  stats: Record<string, any>;
  journeys: JourneyValidation[];
  journeys_ok: number;
}

export interface ComparePayload {
  scenario_id: string;
  before: Side;
  after: Side;
  delta: Record<string, number>;
}

const STAT_ROWS: { key: string; label: string }[] = [
  { key: "nodes", label: "Graph nodes" },
  { key: "edges", label: "Relationships" },
  { key: "services", label: "Services" },
  { key: "operations", label: "Operations" },
  { key: "schemas", label: "Schemas" },
  { key: "fields", label: "Fields" },
  { key: "domains", label: "Domains" },
  { key: "journeys", label: "Journeys" },
  { key: "risks", label: "Findings" },
  { key: "observed_edges", label: "Stated relationships" },
  { key: "inferred_edges", label: "Inferred relationships" },
  { key: "user_edges", label: "Relationships you created" },
];

function Delta({ value, invert }: { value: number; invert?: boolean }) {
  if (!value) {
    return (
      <span className="flex items-center gap-1 text-[var(--color-dim)]">
        <Minus size={11} aria-hidden />
        no change
      </span>
    );
  }
  const good = invert ? value < 0 : value > 0;
  const Icon = value > 0 ? TrendingUp : TrendingDown;
  return (
    <span
      className={cx(
        "flex items-center gap-1",
        good ? "text-[var(--color-ok)]" : "text-[var(--color-broken)]",
      )}
    >
      <Icon size={11} aria-hidden />
      <span className="numeral">
        {value > 0 ? "+" : ""}
        {value}
      </span>
    </span>
  );
}

export function ComparePanel({ data }: { data: ComparePayload | null }) {
  if (!data) {
    return (
      <Card className="p-5">
        <EmptyState
          title="Nothing to compare yet"
          body="Add at least one change to the scenario and the base graph and the changed graph will be shown side by side."
        />
      </Card>
    );
  }

  const journeyDelta =
    data.delta?.journeys_ok ?? data.after.journeys_ok - data.before.journeys_ok;

  const journeyRows = data.before.journeys.map((before) => ({
    before,
    after: data.after.journeys.find((item) => item.journey_id === before.journey_id) ?? null,
  }));

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <SectionTitle>Journeys that still validate</SectionTitle>
        <div className="grid grid-cols-3 gap-px overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-line)]">
          <div className="bg-[var(--color-surface)] p-4">
            <p className="label-eyebrow">Before</p>
            <p className="numeral mt-1 text-[26px] font-semibold text-[var(--color-ink)]">
              {data.before.journeys_ok}
            </p>
          </div>
          <div className="bg-[var(--color-surface)] p-4">
            <p className="label-eyebrow">After</p>
            <p className="numeral mt-1 text-[26px] font-semibold text-[var(--color-ink)]">
              {data.after.journeys_ok}
            </p>
          </div>
          <div className="bg-[var(--color-surface)] p-4">
            <p className="label-eyebrow">Delta</p>
            <p className="mt-2 text-[13px] font-medium">
              <Delta value={journeyDelta} />
            </p>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <SectionTitle>Graph statistics</SectionTitle>
        <div className="scroll-x">
          <table className="w-full border-collapse text-[12.5px]">
            <caption className="sr-only">
              Graph statistics for the base project and for the scenario, with the difference.
            </caption>
            <thead>
              <tr className="border-b border-[var(--color-line)]">
                <th scope="col" className="px-3 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  Measure
                </th>
                <th scope="col" className="px-3 py-2 text-right text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  Before
                </th>
                <th scope="col" className="px-3 py-2 text-right text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  After
                </th>
                <th scope="col" className="px-3 py-2 text-right text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  Delta
                </th>
              </tr>
            </thead>
            <tbody>
              {STAT_ROWS.filter(
                (row) =>
                  data.before.stats?.[row.key] !== undefined ||
                  data.after.stats?.[row.key] !== undefined,
              ).map((row) => {
                const before = Number(data.before.stats?.[row.key] ?? 0);
                const after = Number(data.after.stats?.[row.key] ?? 0);
                return (
                  <tr key={row.key} className="border-b border-[var(--color-line)]">
                    <th scope="row" className="px-3 py-2 text-left font-normal text-[var(--color-ink-2)]">
                      {row.label}
                    </th>
                    <td className="numeral px-3 py-2 text-right text-[var(--color-muted)]">{before}</td>
                    <td className="numeral px-3 py-2 text-right text-[var(--color-ink)]">{after}</td>
                    <td className="px-3 py-2">
                      <span className="flex justify-end">
                        <Delta value={after - before} />
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-5">
        <SectionTitle>Journey by journey</SectionTitle>
        <div className="scroll-x">
          <table className="w-full border-collapse text-[12.5px]">
            <caption className="sr-only">Each journey&apos;s validation before and after.</caption>
            <thead>
              <tr className="border-b border-[var(--color-line)]">
                <th scope="col" className="px-3 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  Journey
                </th>
                <th scope="col" className="px-3 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  Before
                </th>
                <th scope="col" className="px-3 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  After
                </th>
                <th scope="col" className="px-3 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                  Summary after the change
                </th>
              </tr>
            </thead>
            <tbody>
              {journeyRows.map(({ before, after }) => (
                <tr key={before.journey_id} className="border-b border-[var(--color-line)]">
                  <th scope="row" className="px-3 py-2 text-left font-normal text-[var(--color-ink)]">
                    {before.journey_name}
                  </th>
                  <td className="px-3 py-2 text-[var(--color-muted)]">
                    {before.ok ? "OK" : "Broken"}
                  </td>
                  <td
                    className={cx(
                      "px-3 py-2",
                      after?.ok ? "text-[var(--color-ok)]" : "text-[var(--color-broken)]",
                    )}
                  >
                    {after ? (after.ok ? "OK" : "Broken") : "—"}
                  </td>
                  <td className="px-3 py-2 text-[var(--color-muted)]">{after?.summary ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
