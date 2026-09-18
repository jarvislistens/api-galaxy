"use client";

/**
 * A mission, as a card.
 *
 * The brief is shown in full rather than teased. A mission is a prompt to use the real
 * product, so hiding the task behind a "Start" button would only add a click.
 */

import { CheckCircle2, Clock, MapPin, Play, Trophy } from "lucide-react";
import * as React from "react";
import { Badge, Button, Card, cx } from "@/components/ui/primitives";
import type { Mission } from "@/lib/types";

const DIFFICULTY_TONE = {
  gentle: "ok",
  tricky: "degraded",
  hard: "broken",
} as const;

export function MissionCard({
  mission,
  active,
  solved,
  onStart,
}: {
  mission: Mission;
  active: boolean;
  solved: boolean;
  onStart: () => void;
}) {
  const minutes = Math.round(mission.estimated_seconds / 60);
  return (
    <Card
      className={cx(
        "flex h-full flex-col p-4 transition-colors duration-150",
        active && "border-[var(--color-accent)]",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[14px] font-semibold tracking-tight text-[var(--color-ink)]">
            {mission.title}
          </h3>
          <p className="mt-0.5 text-[12.5px] text-[var(--color-muted)]">{mission.tagline}</p>
        </div>
        {solved && (
          <Badge tone="ok" icon={<CheckCircle2 size={11} aria-hidden />}>
            solved
          </Badge>
        )}
      </div>

      <p className="mt-2.5 text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
        {mission.brief}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Badge tone={DIFFICULTY_TONE[mission.difficulty] ?? "neutral"}>
          {mission.difficulty}
        </Badge>
        <Badge tone="neutral" icon={<Clock size={10} aria-hidden />}>
          <span className="numeral">~{minutes || 1} min</span>
        </Badge>
        <Badge tone="accent" icon={<Trophy size={10} aria-hidden />}>
          <span className="numeral">{mission.points} points</span>
        </Badge>
      </div>

      <p className="mt-2.5 flex items-start gap-1.5 text-[11.5px] leading-snug text-[var(--color-dim)]">
        <MapPin size={11} className="mt-[2px] shrink-0" aria-hidden />
        <span>
          Where to work: <span className="text-[var(--color-muted)]">{mission.where}</span>
        </span>
      </p>

      <div className="mt-auto pt-3.5">
        <Button
          variant={active ? "secondary" : "primary"}
          size="sm"
          onClick={onStart}
          aria-label={active ? `${mission.title} is already open` : `Start ${mission.title}`}
        >
          <Play size={13} aria-hidden /> {active ? "Open" : solved ? "Play again" : "Start"}
        </Button>
      </div>
    </Card>
  );
}
