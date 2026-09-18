"use client";

/**
 * How much of the input was actually understood, and who interpreted it.
 *
 * A coverage number that only ever reads "fine" is decoration. This panel shows the
 * errors and warnings even when both are zero, so a non-zero value is legible as a
 * change rather than as a new, unfamiliar widget.
 */

import { CircleCheck, CircleAlert, Cpu } from "lucide-react";
import { Badge, Card, InfoNote, ProgressBar, SectionTitle } from "@/components/ui/primitives";
import type { Overview } from "@/lib/types";

export function CoverageCard({
  parseCoverage,
  enrichment,
}: {
  parseCoverage: Record<string, any>;
  enrichment: Overview["enrichment"];
}) {
  const cleanly = Boolean(parseCoverage?.parsed_cleanly);
  const errors = Number(parseCoverage?.errors ?? 0);
  const warnings = Number(parseCoverage?.warnings ?? 0);
  const ratio = Number(parseCoverage?.described_operation_ratio ?? 0);
  const pct = Math.round(Math.max(0, Math.min(1, ratio)) * 100);

  return (
    <section aria-labelledby="coverage-heading">
      <SectionTitle>
        <span id="coverage-heading">Parse coverage and interpretation</span>
      </SectionTitle>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card className="p-4">
          <div className="flex items-start gap-2.5">
            {cleanly ? (
              <CircleCheck size={16} aria-hidden className="mt-[2px] shrink-0 text-[var(--color-ok)]" />
            ) : (
              <CircleAlert
                size={16}
                aria-hidden
                className="mt-[2px] shrink-0 text-[var(--color-degraded)]"
              />
            )}
            <div className="min-w-0">
              <h3 className="text-[13px] font-semibold text-[var(--color-ink)]">
                {cleanly ? "Every document parsed cleanly" : "Some documents needed patience"}
              </h3>
              <p className="mt-0.5 text-[12px] leading-snug text-[var(--color-muted)]">
                Parsing is deterministic. Nothing at this stage was guessed.
              </p>
            </div>
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[12.5px] sm:grid-cols-3">
            <Stat label="Documents" value={parseCoverage?.services} />
            <Stat label="Operations" value={parseCoverage?.operations} />
            <Stat label="Schemas" value={parseCoverage?.schemas} />
            <Stat label="Fields" value={parseCoverage?.fields} />
            <Stat label="Errors" value={errors} tone={errors > 0 ? "broken" : undefined} />
            <Stat label="Warnings" value={warnings} tone={warnings > 0 ? "degraded" : undefined} />
          </dl>

          <div className="mt-4">
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="text-[12.5px] text-[var(--color-ink-2)]">
                Operations carrying a description
              </span>
              <span className="numeral text-[13px] font-semibold text-[var(--color-ink)]">
                {pct}%
              </span>
            </div>
            <ProgressBar value={ratio} label={`${pct}% of operations carry a description`} />
            <p className="mt-1.5 text-[11.5px] text-[var(--color-dim)]">
              Descriptions are what the interpretation step reads. Below roughly 60%, treat
              every inferred relationship with more suspicion.
            </p>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-start gap-2.5">
            <Cpu size={16} aria-hidden className="mt-[2px] shrink-0 text-[var(--color-accent-soft)]" />
            <div className="min-w-0 flex-1">
              <h3 className="text-[13px] font-semibold text-[var(--color-ink)]">
                AI enrichment status
              </h3>
              <p className="mt-0.5 text-[12px] leading-snug text-[var(--color-muted)]">
                Who produced the parts of this model that nothing states outright.
              </p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge tone={enrichment.is_bundled ? "inferred" : "accent"}>{enrichment.label}</Badge>
            {enrichment.is_bundled && <Badge tone="neutral">Pre-computed · nothing ran</Badge>}
          </div>

          {enrichment.warnings.length > 0 ? (
            <ul className="mt-3 space-y-1.5" aria-label="Enrichment warnings">
              {enrichment.warnings.map((warning) => (
                <li
                  key={warning}
                  className="flex items-start gap-2 rounded-[var(--radius-sm)] border border-[color-mix(in_oklab,var(--color-degraded)_34%,transparent)] bg-[color-mix(in_oklab,var(--color-degraded)_10%,transparent)] px-2.5 py-1.5 text-[12px] leading-snug text-[var(--color-ink-2)]"
                >
                  <CircleAlert
                    size={13}
                    aria-hidden
                    className="mt-[2px] shrink-0 text-[var(--color-degraded)]"
                  />
                  <span>{warning}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-[12px] text-[var(--color-dim)]">
              No warnings were raised during interpretation.
            </p>
          )}

          <div className="mt-3">
            <InfoNote>
              Inferred relationships are drawn dashed everywhere in the app and can be
              accepted, edited or rejected one at a time. Rejecting one never edits your
              source documents.
            </InfoNote>
          </div>
        </Card>
      </div>
    </section>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: unknown;
  tone?: "broken" | "degraded";
}) {
  const colour =
    tone === "broken"
      ? "text-[var(--color-broken)]"
      : tone === "degraded"
        ? "text-[var(--color-degraded)]"
        : "text-[var(--color-ink-2)]";
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-[var(--color-line)] py-1">
      <dt className="text-[var(--color-dim)]">{label}</dt>
      <dd className={`numeral font-medium ${colour}`}>
        {typeof value === "number" ? value.toLocaleString() : "—"}
      </dd>
    </div>
  );
}
