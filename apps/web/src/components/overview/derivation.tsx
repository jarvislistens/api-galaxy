"use client";

/**
 * "How was this derived?"
 *
 * This is a product control, not a footnote. Anything on this page that was *worked out*
 * rather than *read* has to be traceable back to the step that produced it, and the user
 * must be able to reach that explanation without hunting. So the four steps are visible
 * on the page, expandable in place, and also available as a full-page explanation.
 */

import { ScrollText } from "lucide-react";
import * as React from "react";
import {
  Accordion,
  AccordionItem,
  Badge,
  Button,
  Card,
  Dialog,
  InfoNote,
} from "@/components/ui/primitives";
import type { Overview } from "@/lib/types";

const STEP_BLURB: Record<string, string> = {
  Parse: "Read the documents. No judgement applied.",
  Build: "Turn what was read into nodes and relationships.",
  Analyse: "Run the rules that look for trouble.",
  Interpret: "Propose the things nothing actually states.",
};

export function DerivationCard({
  derivation,
  parseCoverage,
  enrichment,
}: {
  derivation: Overview["derivation"];
  parseCoverage: Record<string, any>;
  enrichment: Overview["enrichment"];
}) {
  const [open, setOpen] = React.useState(false);

  return (
    <Card className="px-4 py-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-eyebrow">Provenance</p>
          <h2 className="mt-1 text-[15px] font-semibold tracking-tight text-[var(--color-ink)]">
            How was this derived?
          </h2>
          <p className="mt-1 max-w-2xl text-[12.5px] leading-snug text-[var(--color-muted)]">
            Four steps ran between your documents and this page. Two of them read; two of
            them reason. Everything a step reasoned about is labelled as such wherever it
            appears.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
          <ScrollText size={13} aria-hidden />
          Read the full explanation
        </Button>
      </div>

      <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface-2)]/40 px-3">
        <Accordion type="multiple" defaultValue={["step-0"]}>
          {derivation.map((step, index) => (
            <AccordionItem
              key={step.step}
              value={`step-${index}`}
              trigger={
                <span className="flex min-w-0 items-center gap-2.5">
                  <span className="numeral flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--color-line-strong)] text-[11px] text-[var(--color-muted)]">
                    {index + 1}
                  </span>
                  <span className="truncate">{step.step}</span>
                  <span className="hidden truncate text-[12px] font-normal text-[var(--color-dim)] sm:inline">
                    {STEP_BLURB[step.step] ?? ""}
                  </span>
                </span>
              }
            >
              <p className="pl-[30px] pr-2 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
                {step.detail}
              </p>
            </AccordionItem>
          ))}
        </Accordion>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge tone={parseCoverage?.parsed_cleanly ? "ok" : "degraded"}>
          {parseCoverage?.parsed_cleanly
            ? "Parsed cleanly · 0 errors"
            : `Parsed with ${parseCoverage?.errors ?? 0} error(s)`}
        </Badge>
        <Badge tone={enrichment.is_bundled ? "inferred" : "accent"}>
          Interpretation: {enrichment.label}
        </Badge>
        <span className="text-[11.5px] text-[var(--color-dim)]">
          {parseCoverage?.services ?? 0} document(s) · {parseCoverage?.operations ?? 0} operations ·{" "}
          {parseCoverage?.schemas ?? 0} schemas
        </span>
      </div>

      <Dialog
        open={open}
        onOpenChange={setOpen}
        wide
        title="How this estate was derived"
        description="Read top to bottom. Each step only uses what the step above it produced."
      >
        <ol className="space-y-3">
          {derivation.map((step, index) => (
            <li
              key={step.step}
              className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface)] p-3.5"
            >
              <div className="flex items-center gap-2.5">
                <span className="numeral flex h-6 w-6 items-center justify-center rounded-full bg-[var(--color-surface-3)] text-[12px] font-semibold text-[var(--color-ink-2)]">
                  {index + 1}
                </span>
                <h3 className="text-[13.5px] font-semibold text-[var(--color-ink)]">{step.step}</h3>
                <span className="text-[12px] text-[var(--color-dim)]">
                  {STEP_BLURB[step.step] ?? ""}
                </span>
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
                {step.detail}
              </p>
            </li>
          ))}
        </ol>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] p-3.5">
            <p className="label-eyebrow">Parse coverage</p>
            <dl className="mt-2 space-y-1 text-[12.5px]">
              <Row label="Documents" value={parseCoverage?.services} />
              <Row label="Operations" value={parseCoverage?.operations} />
              <Row label="Schemas" value={parseCoverage?.schemas} />
              <Row label="Fields" value={parseCoverage?.fields} />
              <Row label="Errors" value={parseCoverage?.errors} />
              <Row label="Warnings" value={parseCoverage?.warnings} />
            </dl>
          </div>
          <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] p-3.5">
            <p className="label-eyebrow">Interpretation</p>
            <p className="mt-2 text-[13px] text-[var(--color-ink-2)]">{enrichment.label}</p>
            <p className="mt-2 text-[12px] leading-snug text-[var(--color-muted)]">
              {enrichment.is_bundled
                ? "This project ships with a pre-computed interpretation so the demo is identical every time and needs no model running."
                : "Produced on this machine by the configured provider."}
            </p>
            {enrichment.warnings.length > 0 && (
              <ul className="mt-2 space-y-1">
                {enrichment.warnings.map((warning) => (
                  <li key={warning} className="text-[12px] text-[var(--color-degraded)]">
                    {warning}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="mt-4">
          <InfoNote>
            Nothing on this page was invented at display time. Every inferred relationship
            keeps the rule or model that proposed it, and you can reject any of them.
          </InfoNote>
        </div>
      </Dialog>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[var(--color-dim)]">{label}</dt>
      <dd className="numeral text-[var(--color-ink-2)]">
        {typeof value === "number" ? value.toLocaleString() : "—"}
      </dd>
    </div>
  );
}
