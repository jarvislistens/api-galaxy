"use client";

/**
 * What you have already asked, this session.
 *
 * Deliberately in memory only: a question history is a record of what someone was
 * thinking, and this product does not keep those without being asked to.
 */

import { History, RotateCw } from "lucide-react";
import * as React from "react";
import { Badge, Button, Card, SectionTitle } from "@/components/ui/primitives";

export interface HistoryEntry {
  id: string;
  question: string;
  provider: string;
  grounded: boolean;
  confidence: number;
  at: number;
}

export function QuestionHistory({
  entries,
  onRerun,
  onClear,
}: {
  entries: HistoryEntry[];
  onRerun: (entry: HistoryEntry) => void;
  onClear: () => void;
}) {
  return (
    <Card className="p-3.5">
      <SectionTitle
        action={
          entries.length > 0 ? (
            <Button variant="quiet" size="sm" onClick={onClear}>
              Clear
            </Button>
          ) : undefined
        }
      >
        <span className="flex items-center gap-1.5">
          <History size={13} className="text-[var(--color-dim)]" aria-hidden />
          This session
        </span>
      </SectionTitle>

      {entries.length === 0 ? (
        <p className="text-[12px] text-[var(--color-dim)]">
          Questions you ask appear here so you can run them again. Nothing is written to
          disk.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {entries.map((entry) => (
            <li key={entry.id}>
              <button
                onClick={() => onRerun(entry)}
                className="flex w-full items-start gap-2 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-2.5 py-2 text-left transition-colors duration-150 hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-3)]"
              >
                <RotateCw
                  size={12}
                  className="mt-[3px] shrink-0 text-[var(--color-dim)]"
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] leading-snug text-[var(--color-ink-2)]">
                    {entry.question}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5">
                    <Badge tone="neutral">{entry.provider}</Badge>
                    <Badge tone={entry.grounded ? "ok" : "broken"}>
                      {entry.grounded ? "grounded" : "ungrounded"}
                    </Badge>
                    <span className="numeral text-[10.5px] text-[var(--color-dim)]">
                      {Math.round(entry.confidence * 100)}% confidence
                    </span>
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
