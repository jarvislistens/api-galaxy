"use client";

/**
 * What is inside every report, stated once and plainly.
 *
 * A report that leaves its own provenance out is a report you cannot check a year later, so
 * the list below is a promise about the artefact rather than a feature list.
 */

import { FileText, MousePointerClick } from "lucide-react";
import * as React from "react";
import { Badge, Card, SectionTitle } from "@/components/ui/primitives";
import { LEGEND_EDGES } from "@/components/graph/graph-style";

const CONTENTS = [
  { term: "Project name", detail: "The estate the report was produced from." },
  { term: "Generation time", detail: "When this specific file was produced." },
  {
    term: "Specification fingerprint",
    detail: "A hash of the parsed input, so two reports from the same spec are provably the same input.",
  },
  { term: "App version", detail: "Which build of API Galaxy produced it." },
  {
    term: "Active scenario",
    detail: "Named if the report was generated with a scenario applied, absent if it was not.",
  },
  {
    term: "Provider disclosure",
    detail: "Which provider and model contributed inference, or that none did.",
  },
  {
    term: "Fact vs inference legend",
    detail: "The same legend as the app, so a reader who has never seen the tool can still read the diagram.",
  },
];

export function DisclosurePanel({ note }: { note?: string }) {
  return (
    <Card className="p-5">
      <SectionTitle>What every report contains</SectionTitle>

      <dl className="space-y-2">
        {CONTENTS.map((item) => (
          <div key={item.term} className="grid gap-1 sm:grid-cols-[190px_1fr] sm:gap-3">
            <dt className="text-[12.5px] font-medium text-[var(--color-ink-2)]">{item.term}</dt>
            <dd className="text-[12.5px] leading-snug text-[var(--color-muted)]">{item.detail}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-4 border-t border-[var(--color-line)] pt-4">
        <p className="label-eyebrow mb-2">The legend that ships inside every diagram</p>
        <ul className="space-y-1.5">
          {LEGEND_EDGES.map((entry) => (
            <li key={entry.stroke} className="flex items-center gap-2.5 text-[12.5px]">
              <svg width="34" height="8" viewBox="0 0 34 8" aria-hidden className="shrink-0">
                <line
                  x1="0"
                  y1="4"
                  x2="34"
                  y2="4"
                  stroke={
                    entry.tone === "fact"
                      ? "var(--color-fact)"
                      : entry.tone === "inferred"
                        ? "var(--color-inferred)"
                        : "var(--color-user)"
                  }
                  strokeWidth="1.6"
                  strokeDasharray={
                    entry.stroke === "dashed" ? "5 3" : entry.stroke === "dotted" ? "1.5 3" : undefined
                  }
                />
              </svg>
              <Badge tone={entry.tone}>{entry.stroke}</Badge>
              <span className="text-[var(--color-muted)]">{entry.label}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4 flex flex-col gap-2 border-t border-[var(--color-line)] pt-4">
        <p className="flex items-start gap-2 text-[12.5px] leading-snug text-[var(--color-ink-2)]">
          <MousePointerClick size={13} className="mt-[2px] shrink-0 text-[var(--color-accent-soft)]" aria-hidden />
          <span>
            <strong className="font-medium">The HTML report is the interactive one.</strong> It
            opens from a file with search, pan and zoom, a node inspector and journey playback,
            and it makes no network requests.
          </span>
        </p>
        <p className="flex items-start gap-2 text-[12.5px] leading-snug text-[var(--color-ink-2)]">
          <FileText size={13} className="mt-[2px] shrink-0 text-[var(--color-dim)]" aria-hidden />
          <span>
            <strong className="font-medium">The PDF is static.</strong> It is a paginated
            document with print-safe colours — good for a review pack, not for exploring.
          </span>
        </p>
      </div>

      {note && (
        <p className="mt-4 border-t border-[var(--color-line)] pt-3 text-[12px] leading-snug text-[var(--color-muted)]">
          {note}
        </p>
      )}
    </Card>
  );
}
