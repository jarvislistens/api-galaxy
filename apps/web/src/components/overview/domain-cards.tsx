"use client";

/**
 * Business domains, not files.
 *
 * Seven specifications arrive as seven documents; a reader thinks in areas of the
 * business. Each card is a real button so it is keyboard reachable, and it carries the
 * counts that decide where somebody looks first.
 */

import { ArrowUpRight, ShieldAlert } from "lucide-react";
import { Badge, SectionTitle } from "@/components/ui/primitives";
import type { Overview } from "@/lib/types";

export function DomainCards({
  domains,
  onOpen,
}: {
  domains: Overview["domains"];
  onOpen: (domainId: string) => void;
}) {
  return (
    <section aria-labelledby="domains-heading">
      <SectionTitle>
        <span id="domains-heading">
          Business domains
          <span className="ml-2 numeral text-[12px] font-normal text-[var(--color-dim)]">
            {domains.length}
          </span>
        </span>
      </SectionTitle>
      <p className="-mt-2 mb-3 text-[12.5px] text-[var(--color-muted)]">
        Grouped from the services that own the same data. Open one to see it filtered in the
        galaxy.
      </p>

      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {domains.map((domain) => (
          <li key={domain.id}>
            <button
              type="button"
              onClick={() => onOpen(domain.id)}
              className="group panel h-full w-full p-3.5 text-left transition-[border-color,background] duration-200 ease-[var(--ease-out-quint)] hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-2)]"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-[13.5px] font-semibold text-[var(--color-ink)]">
                  {domain.name}
                </h3>
                <ArrowUpRight
                  size={14}
                  aria-hidden
                  className="mt-0.5 shrink-0 text-[var(--color-dim)] transition-colors duration-150 group-hover:text-[var(--color-accent-soft)]"
                />
              </div>

              <p className="mt-1 line-clamp-2 text-[12px] leading-snug text-[var(--color-muted)]">
                {domain.description}
              </p>

              <p className="mt-2.5 text-[11.5px] text-[var(--color-ink-2)]">
                {domain.services.join(", ")}
              </p>

              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <Badge tone="neutral">
                  <span className="numeral">{domain.operation_count}</span>&nbsp;operations
                </Badge>
                {domain.risk_count > 0 ? (
                  <Badge tone="degraded" icon={<ShieldAlert size={11} aria-hidden />}>
                    <span className="numeral">{domain.risk_count}</span>&nbsp;
                    {domain.risk_count === 1 ? "finding" : "findings"}
                  </Badge>
                ) : (
                  <Badge tone="ok">No findings</Badge>
                )}
                <Badge tone="neutral">
                  <span className="numeral">{domain.services.length}</span>&nbsp;
                  {domain.services.length === 1 ? "service" : "services"}
                </Badge>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
