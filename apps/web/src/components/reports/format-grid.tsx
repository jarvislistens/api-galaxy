"use client";

/**
 * The export catalogue.
 *
 * A format the backend reports as unavailable is rendered disabled with its
 * `unavailable_reason` visible. It is never hidden and never left as a button that fails
 * when pressed — a dead control teaches the reader that the UI lies.
 */

import { Ban, MousePointerClick } from "lucide-react";
import * as React from "react";
import { Badge, cx } from "@/components/ui/primitives";
import type { ExportFormat } from "@/lib/types";

export function FormatGrid({
  formats,
  selected,
  onSelect,
}: {
  formats: ExportFormat[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul
      className="grid gap-3 md:grid-cols-2 xl:grid-cols-3"
      aria-label="Available report formats"
    >
      {formats.map((format) => {
        const active = selected === format.id;
        const disabled = !format.available;
        return (
          <li key={format.id}>
            <button
              type="button"
              onClick={() => !disabled && onSelect(format.id)}
              disabled={disabled}
              aria-pressed={active}
              aria-describedby={disabled ? `${format.id}-unavailable` : undefined}
              className={cx(
                "flex h-full w-full flex-col rounded-[var(--radius-lg)] border p-4 text-left",
                "transition-colors duration-200",
                disabled && "cursor-not-allowed opacity-60",
                active
                  ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_10%,transparent)]"
                  : "border-[var(--color-line)] bg-[var(--color-surface)] hover:border-[var(--color-line-strong)]",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-[13.5px] font-semibold text-[var(--color-ink)]">
                  {format.label}
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {format.interactive && (
                    <Badge tone="accent" icon={<MousePointerClick size={10} aria-hidden />}>
                      Interactive
                    </Badge>
                  )}
                  {disabled && (
                    <Badge tone="neutral" icon={<Ban size={10} aria-hidden />}>
                      Unavailable
                    </Badge>
                  )}
                </span>
              </div>

              <p className="mt-2 flex-1 text-[12.5px] leading-snug text-[var(--color-muted)]">
                {format.description}
              </p>

              <p className="mono mt-3 text-[11px] text-[var(--color-dim)]">{format.extension}</p>

              {disabled && (
                <p
                  id={`${format.id}-unavailable`}
                  className="mt-2 border-t border-[var(--color-line)] pt-2 text-[12px] leading-snug text-[var(--color-degraded)]"
                >
                  {format.unavailable_reason ||
                    "This installation is missing a dependency this format needs."}
                </p>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
