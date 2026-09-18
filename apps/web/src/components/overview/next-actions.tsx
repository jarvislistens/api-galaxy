"use client";

/**
 * Three ways out of this page.
 *
 * An overview that ends in a wall of numbers leaves the reader to invent their own next
 * move. These are the three that actually pay off first, in the order they pay off.
 */

import { ArrowRight, FlaskConical, MessageSquareText, Route } from "lucide-react";
import Link from "next/link";
import { SectionTitle } from "@/components/ui/primitives";

export function NextActions({ base, topJourneyId }: { base: string; topJourneyId?: string }) {
  const actions = [
    {
      href: topJourneyId
        ? `${base}/journeys?journey=${encodeURIComponent(topJourneyId)}`
        : `${base}/journeys`,
      icon: Route,
      title: "Play a journey",
      body: "Watch one business flow move through the estate, step by step, with the evidence for each hop.",
      cue: "Start here if you are new to this estate",
    },
    {
      href: `${base}/ask`,
      icon: MessageSquareText,
      title: "Ask a question",
      body: "Ask in English and get the path through the graph, with a citation on every hop and invented references discarded.",
      cue: "Start here if you have a specific question",
    },
    {
      href: `${base}/break-lab`,
      icon: FlaskConical,
      title: "Break something on purpose",
      body: "Rename a field or remove an endpoint and see the blast radius — broken, degraded, possibly affected — before production does.",
      cue: "Start here if you are planning a change",
    },
  ];

  return (
    <section aria-labelledby="next-heading">
      <SectionTitle>
        <span id="next-heading">What next</span>
      </SectionTitle>

      <ul className="grid gap-3 lg:grid-cols-3">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <li key={action.href}>
              <Link
                href={action.href}
                className="group panel flex h-full flex-col p-4 transition-[border-color,background] duration-200 ease-[var(--ease-out-quint)] hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-2)]"
              >
                <Icon size={16} aria-hidden className="text-[var(--color-accent-soft)]" />
                <h3 className="mt-2.5 flex items-center gap-1.5 text-[13.5px] font-semibold text-[var(--color-ink)]">
                  {action.title}
                  <ArrowRight
                    size={13}
                    aria-hidden
                    className="text-[var(--color-dim)] transition-transform duration-200 ease-[var(--ease-out-quint)] group-hover:translate-x-0.5 group-hover:text-[var(--color-accent-soft)]"
                  />
                </h3>
                <p className="mt-1 flex-1 text-[12.5px] leading-snug text-[var(--color-muted)]">
                  {action.body}
                </p>
                <p className="label-eyebrow mt-3">{action.cue}</p>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
