"use client";

/**
 * Chaos mode.
 *
 * A real breaking change is applied to a throwaway scenario and the blast radius is shown
 * in full — minus the one row that would give the answer away. Everything here is the
 * same impact data Break Lab shows; nothing is simplified for the game.
 */

import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, CircleDashed, HelpCircle, Shuffle, TriangleAlert } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  InfoNote,
  LoadingBlock,
  SectionTitle,
  cx,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { ImpactPayload, ImpactStatus } from "@/lib/types";

const STATUS: Record<ImpactStatus, { label: string; tone: "broken" | "degraded" | "possible" | "neutral"; icon: React.ReactNode }> = {
  broken: { label: "broken", tone: "broken", icon: <AlertTriangle size={11} aria-hidden /> },
  degraded: { label: "degraded", tone: "degraded", icon: <TriangleAlert size={11} aria-hidden /> },
  potentially_affected: {
    label: "possibly affected",
    tone: "possible",
    icon: <HelpCircle size={11} aria-hidden />,
  },
  unaffected: { label: "unaffected", tone: "neutral", icon: <CircleDashed size={11} aria-hidden /> },
};

export function ChaosRun({
  projectId,
  payload,
  onPayload,
  guess,
  onGuess,
  onInspect,
}: {
  projectId: string;
  payload: ImpactPayload | null;
  onPayload: (payload: ImpactPayload) => void;
  guess: string;
  onGuess: (nodeId: string) => void;
  onInspect?: (nodeId: string) => void;
}) {
  const [seed, setSeed] = React.useState(() => Math.floor(Math.random() * 100000));

  const run = useMutation({
    mutationFn: (value: number) => api.chaos(projectId, value),
    onSuccess: onPayload,
  });

  const start = () => {
    const next = Math.floor(Math.random() * 100000);
    setSeed(next);
    run.mutate(next);
  };

  if (!payload) {
    return (
      <Card className="p-4">
        <SectionTitle>Chaos run</SectionTitle>
        <p className="text-[12.5px] leading-relaxed text-[var(--color-muted)]">
          A safe, random breaking change will be applied to a throwaway scenario. Your
          source files are never touched. You will see the full blast radius — but not the
          node it started from.
        </p>
        <div className="mt-3 flex items-center gap-2">
          <Button variant="primary" size="sm" loading={run.isPending} onClick={start}>
            <Shuffle size={13} aria-hidden /> Start chaos run
          </Button>
          <span className="numeral text-[11.5px] text-[var(--color-dim)]">seed {seed}</span>
        </div>
        {run.isPending && (
          <div className="mt-3">
            <LoadingBlock label="Applying a random breaking change" rows={3} />
          </div>
        )}
        {run.error && (
          <div className="mt-3">
            <ErrorState
              title="The chaos run could not start"
              detail={(run.error as ApiError).message}
              correlationId={(run.error as ApiError).correlationId}
              onRetry={start}
            />
          </div>
        )}
      </Card>
    );
  }

  const shockwave = payload.shockwave ?? [];
  const candidates = payload.candidates ?? [];
  const brokenJourneys = (payload.journeys ?? []).filter((journey) => !journey.ok);

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <SectionTitle
          action={
            <Button variant="ghost" size="sm" loading={run.isPending} onClick={start}>
              <Shuffle size={13} aria-hidden /> New run
            </Button>
          }
        >
          The blast radius
        </SectionTitle>
        <p className="text-[12.5px] text-[var(--color-muted)]">
          {payload.scenario.changes[0]?.label ?? "A change was applied."} Scenario{" "}
          <span className="mono text-[var(--color-ink-2)]">{payload.scenario.id}</span>.
        </p>

        <div className="scroll-x mt-3">
          <table className="w-full min-w-[520px] border-collapse text-left">
            <caption className="sr-only">
              Impact of the hidden change, by status and distance. The origin row is
              deliberately withheld.
            </caption>
            <thead>
              <tr className="border-b border-[var(--color-line)]">
                <th scope="col" className="label-eyebrow py-1.5 pr-3">Status</th>
                <th scope="col" className="label-eyebrow py-1.5 pr-3">Hops</th>
                <th scope="col" className="label-eyebrow py-1.5 pr-3">Node</th>
                <th scope="col" className="label-eyebrow py-1.5">Why</th>
              </tr>
            </thead>
            <tbody>
              {shockwave.map((item) => {
                const status = STATUS[item.status] ?? STATUS.unaffected;
                return (
                  <tr key={item.node_id} className="border-b border-[var(--color-line)] align-top">
                    <td className="py-2 pr-3">
                      <Badge tone={status.tone} icon={status.icon}>
                        {status.label}
                      </Badge>
                    </td>
                    <td className="numeral py-2 pr-3 text-[12px] text-[var(--color-ink-2)]">
                      {item.distance}
                    </td>
                    <td className="py-2 pr-3">
                      <button
                        onClick={() => onInspect?.(item.node_id)}
                        className="text-left text-[12.5px] text-[var(--color-ink)] transition-colors hover:text-[var(--color-accent-soft)]"
                      >
                        {item.node_label}
                        <span className="mono block break-all text-[10.5px] text-[var(--color-dim)]">
                          {item.node_id}
                        </span>
                      </button>
                    </td>
                    <td className="py-2 text-[12px] leading-snug text-[var(--color-muted)]">
                      {item.reason}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {shockwave.length === 0 && (
          <p className="mt-2 text-[12.5px] text-[var(--color-dim)]">
            This change produced no measurable impact. Start another run.
          </p>
        )}

        <div className="mt-3">
          <InfoNote>
            The node at distance 0 — the origin — has been removed from this table on
            purpose. Everything else is exactly what Break Lab would show you.
          </InfoNote>
        </div>
      </Card>

      {brokenJourneys.length > 0 && (
        <Card className="p-4">
          <SectionTitle>Journeys that stopped validating</SectionTitle>
          <ul className="space-y-2">
            {brokenJourneys.map((journey) => (
              <li
                key={journey.journey_id}
                className="rounded-[var(--radius-sm)] border border-[color-mix(in_oklab,var(--color-broken)_34%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_8%,transparent)] px-3 py-2"
              >
                <p className="flex items-center gap-1.5 text-[12.5px] font-medium text-[var(--color-ink)]">
                  <AlertTriangle size={12} className="text-[var(--color-broken)]" aria-hidden />
                  {journey.journey_name}
                </p>
                <p className="mt-0.5 text-[12px] text-[var(--color-ink-2)]">{journey.summary}</p>
                <ul className="mt-1 space-y-0.5">
                  {journey.steps
                    .filter((step) => !step.ok)
                    .map((step) => (
                      <li key={step.step_id} className="text-[11.5px] text-[var(--color-muted)]">
                        <span className="mono text-[var(--color-dim)]">{step.step_id}</span> —{" "}
                        {step.reasons.join(" ")}
                      </li>
                    ))}
                </ul>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="p-4">
        <SectionTitle>Which node did this start from?</SectionTitle>
        <ul className="grid gap-1.5 sm:grid-cols-2" role="radiogroup" aria-label="Candidate origins">
          {candidates.map((candidate) => {
            const picked = guess === candidate.id;
            return (
              <li key={candidate.id}>
                <button
                  role="radio"
                  aria-checked={picked}
                  onClick={() => onGuess(candidate.id)}
                  className={cx(
                    "flex w-full items-start gap-2 rounded-[var(--radius-sm)] border px-2.5 py-2 text-left transition-colors duration-150",
                    picked
                      ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_14%,transparent)]"
                      : "border-[var(--color-line)] bg-[var(--color-surface-2)] hover:border-[var(--color-line-strong)]",
                  )}
                >
                  <span
                    className={cx(
                      "mt-[3px] h-3 w-3 shrink-0 rounded-full border",
                      picked
                        ? "border-[var(--color-accent)] bg-[var(--color-accent)]"
                        : "border-[var(--color-line-strong)]",
                    )}
                    aria-hidden
                  />
                  <span className="min-w-0">
                    <span className="mono block truncate text-[12px] text-[var(--color-ink)]">
                      {candidate.label}
                    </span>
                    <span className="mono block break-all text-[10.5px] text-[var(--color-dim)]">
                      {candidate.id}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {candidates.length === 0 && (
          <p className="text-[12.5px] text-[var(--color-dim)]">
            This run returned no candidate list. Start another run.
          </p>
        )}
      </Card>
    </div>
  );
}
