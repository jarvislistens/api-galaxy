"use client";

/**
 * The mission workspace.
 *
 * The rule this file exists to enforce: the game layer is chrome. Every real label, node
 * ID and finding stays visible, the timer counts up rather than down, and hints are opt-in
 * and priced honestly. Nothing here replaces the product — it points at it.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowUpRight,
  Check,
  CheckCircle2,
  Copy,
  Lightbulb,
  Timer,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ChaosRun } from "@/components/missions/chaos-run";
import { NodePicker } from "@/components/missions/node-picker";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  InfoNote,
  SectionTitle,
  cx,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { ImpactPayload, Mission, MissionResult } from "@/lib/types";

const HINT_COST = 20;

function useElapsedSeconds(startedAt: number, running: boolean) {
  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    if (!running) return;
    setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [startedAt, running]);
  return elapsed;
}

function formatClock(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function Checkbox({
  checked,
  onChange,
  label,
  detail,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  detail: string;
}) {
  return (
    <button
      role="checkbox"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cx(
        "flex w-full items-start gap-2.5 rounded-[var(--radius-sm)] border px-3 py-2.5 text-left transition-colors duration-150",
        checked
          ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_12%,transparent)]"
          : "border-[var(--color-line)] bg-[var(--color-surface-2)] hover:border-[var(--color-line-strong)]",
      )}
    >
      <span
        className={cx(
          "mt-[2px] flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border",
          checked
            ? "border-[var(--color-accent)] bg-[var(--color-accent)]"
            : "border-[var(--color-line-strong)]",
        )}
        aria-hidden
      >
        {checked && <Check size={11} className="text-[#0a0c10]" />}
      </span>
      <span className="min-w-0">
        <span className="block text-[12.5px] font-medium text-[var(--color-ink)]">{label}</span>
        <span className="block text-[11.5px] leading-snug text-[var(--color-muted)]">{detail}</span>
      </span>
    </button>
  );
}

export function ActiveMission({
  projectId,
  mission,
  onExit,
  onSolved,
}: {
  projectId: string;
  mission: Mission;
  onExit: () => void;
  onSolved: (missionId: string, score: number) => void;
}) {
  const select = useWorkspace((s) => s.select);
  const toast = useWorkspace((s) => s.toast);
  const activeScenarioId = useWorkspace((s) => s.activeScenarioId);
  const reducedMotion = useReducedMotion();

  const [startedAt] = React.useState(() => Date.now());
  const [hintsUsed, setHintsUsed] = React.useState(0);
  const [nodeIds, setNodeIds] = React.useState<string[]>([]);
  const [chaos, setChaos] = React.useState<ImpactPayload | null>(null);
  const [chaosGuess, setChaosGuess] = React.useState("");
  const [checks, setChecks] = React.useState({
    rename_applied: false,
    all_journeys_valid: false,
    repairs_applied: false,
  });
  const [result, setResult] = React.useState<MissionResult | null>(null);

  const elapsed = useElapsedSeconds(startedAt, result === null || !result.correct);

  // A scenario mission reads the real Break Lab state when there is one, rather than
  // asking the user to describe what they did.
  const scenarioState = useQuery({
    queryKey: ["impact", projectId, activeScenarioId],
    queryFn: () => api.impact(projectId, activeScenarioId!),
    enabled: mission.answer_kind === "scenario" && Boolean(activeScenarioId),
  });

  React.useEffect(() => {
    const payload = scenarioState.data;
    if (!payload) return;
    setChecks({
      rename_applied: payload.scenario.changes.some((change) => change.kind === "rename_field"),
      all_journeys_valid:
        (payload.all_journeys ?? []).length > 0 &&
        (payload.all_journeys ?? []).every((journey) => journey.ok),
      repairs_applied: (payload.scenario.repairs ?? []).some(
        (repair) => repair.status === "applied",
      ),
    });
  }, [scenarioState.data]);

  const check = useMutation({
    mutationFn: (attempt: Record<string, any>) =>
      api.checkMission(projectId, mission.id, { ...attempt, hints_used: hintsUsed }),
    onSuccess: (outcome) => {
      setResult(outcome);
      if (outcome.correct) onSolved(mission.id, outcome.score);
    },
  });

  const submit = () => {
    if (mission.id === "chaos-mode") {
      check.mutate({
        node_id: chaosGuess,
        actual_node_id: chaos?.hidden_origin_token ?? "",
      });
      return;
    }
    if (mission.answer_kind === "scenario") {
      check.mutate(checks);
      return;
    }
    if (mission.answer_kind === "nodes") {
      check.mutate({ node_ids: nodeIds });
      return;
    }
    check.mutate({ node_id: nodeIds[0] ?? "" });
  };

  const canSubmit =
    mission.id === "chaos-mode"
      ? Boolean(chaosGuess && chaos)
      : mission.answer_kind === "scenario"
        ? true
        : nodeIds.length > 0;

  const copyResult = async () => {
    if (!result?.share_text) return;
    try {
      await navigator.clipboard.writeText(result.share_text);
      toast("success", "Result copied to the clipboard.");
    } catch {
      toast("error", "The clipboard is not available in this browser.");
    }
  };

  return (
    <Card raised className="p-4">
      {/* ------------------------------------------------------------ header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-eyebrow">Mission in progress</p>
          <h3 className="mt-1 text-[16px] font-semibold tracking-tight text-[var(--color-ink)]">
            {mission.title}
          </h3>
          <p className="mt-0.5 text-[12.5px] text-[var(--color-muted)]">{mission.tagline}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-line)] px-2.5 py-1.5 text-[12px] text-[var(--color-ink-2)]"
            aria-label={`Elapsed time ${formatClock(elapsed)}`}
          >
            <Timer size={12} className="text-[var(--color-dim)]" aria-hidden />
            <span className="numeral">{formatClock(elapsed)}</span>
          </span>
          <Button variant="ghost" size="sm" onClick={onExit} aria-label="Close this mission">
            <X size={14} aria-hidden />
          </Button>
        </div>
      </div>

      <p className="mt-3 text-[13px] leading-relaxed text-[var(--color-ink-2)]">{mission.brief}</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Badge tone="neutral">{mission.difficulty}</Badge>
        <Badge tone="accent">
          <span className="numeral">{mission.points} points</span>
        </Badge>
        <Badge tone="neutral">Work in: {mission.where}</Badge>
      </div>

      <p className="mt-2 text-[11.5px] text-[var(--color-dim)]">
        The clock counts up and is not scored. It is there so you can see how long a real
        investigation takes, not to rush you.
      </p>

      {/* ------------------------------------------------------------- hints */}
      <div className="mt-4 rounded-[var(--radius-md)] border border-[var(--color-line)] p-3.5">
        <SectionTitle
          action={
            hintsUsed < mission.hints.length ? (
              <Button variant="secondary" size="sm" onClick={() => setHintsUsed((n) => n + 1)}>
                <Lightbulb size={13} aria-hidden /> Reveal a hint
              </Button>
            ) : (
              <span className="text-[11.5px] text-[var(--color-dim)]">All hints revealed</span>
            )
          }
        >
          Hints
        </SectionTitle>
        <p className="text-[12px] text-[var(--color-muted)]">
          {hintsUsed} of {mission.hints.length} revealed. Each hint costs{" "}
          <span className="numeral">{HINT_COST}</span> points from your final score
          {hintsUsed > 0 && (
            <>
              {" "}
              — currently{" "}
              <span className="numeral text-[var(--color-degraded)]">
                −{hintsUsed * HINT_COST}
              </span>
            </>
          )}
          .
        </p>
        {hintsUsed > 0 && (
          <ol className="mt-2.5 space-y-1.5">
            {mission.hints.slice(0, hintsUsed).map((hint, position) => (
              <li
                key={hint}
                className="flex items-start gap-2 rounded-[var(--radius-sm)] border border-[color-mix(in_oklab,var(--color-degraded)_30%,transparent)] bg-[color-mix(in_oklab,var(--color-degraded)_8%,transparent)] px-3 py-2"
              >
                <span className="numeral mt-[1px] text-[11px] text-[var(--color-degraded)]">
                  {position + 1}
                </span>
                <span className="text-[12.5px] leading-snug text-[var(--color-ink-2)]">{hint}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* ------------------------------------------------------ answer control */}
      <div className="mt-4">
        <SectionTitle>Your answer</SectionTitle>

        {mission.id === "chaos-mode" ? (
          <ChaosRun
            projectId={projectId}
            payload={chaos}
            onPayload={(payload) => {
              setChaos(payload);
              setChaosGuess("");
              setResult(null);
            }}
            guess={chaosGuess}
            onGuess={setChaosGuess}
            onInspect={select}
          />
        ) : mission.answer_kind === "scenario" ? (
          <div className="space-y-2.5">
            <p className="text-[12.5px] text-[var(--color-muted)]">
              {activeScenarioId
                ? "Read from your active Break Lab scenario. Correct anything that does not match what you actually did."
                : "No Break Lab scenario is active, so confirm each of these yourself."}
            </p>
            {scenarioState.error && (
              <ErrorState
                title="The scenario state could not be read"
                detail={(scenarioState.error as ApiError).message}
                correlationId={(scenarioState.error as ApiError).correlationId}
                onRetry={() => void scenarioState.refetch()}
              />
            )}
            <Checkbox
              checked={checks.rename_applied}
              onChange={(value) => setChecks((current) => ({ ...current, rename_applied: value }))}
              label="The rename has been applied"
              detail="customer_id was renamed in a Break Lab scenario, not in your source files."
            />
            <Checkbox
              checked={checks.repairs_applied}
              onChange={(value) => setChecks((current) => ({ ...current, repairs_applied: value }))}
              label="A repair has been applied"
              detail="An alias mapping or equivalent, rather than undoing the change."
            />
            <Checkbox
              checked={checks.all_journeys_valid}
              onChange={(value) =>
                setChecks((current) => ({ ...current, all_journeys_valid: value }))
              }
              label="Every journey validates again"
              detail="Replayed and passing, not assumed."
            />
            <Link
              href={`/workspace/${projectId}/break-lab`}
              className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-accent-soft)] underline decoration-dotted underline-offset-2"
            >
              Open Break Lab <ArrowUpRight size={12} aria-hidden />
            </Link>
          </div>
        ) : (
          <div className="space-y-2.5">
            <p className="text-[12.5px] text-[var(--color-muted)]">
              {mission.answer_kind === "nodes"
                ? "Select every node that belongs to the answer."
                : "Select the one node that answers this."}
            </p>
            <NodePicker
              projectId={projectId}
              multiple={mission.answer_kind === "nodes"}
              value={nodeIds}
              onChange={setNodeIds}
              onInspect={select}
            />
          </div>
        )}

        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            loading={check.isPending}
            disabled={!canSubmit}
            onClick={submit}
          >
            Check my answer
          </Button>
          {hintsUsed > 0 && (
            <span className="numeral text-[11.5px] text-[var(--color-dim)]">
              {hintsUsed} hint{hintsUsed === 1 ? "" : "s"} used
            </span>
          )}
        </div>

        {check.error && (
          <div className="mt-3">
            <ErrorState
              title="The answer could not be checked"
              detail={(check.error as ApiError).message}
              hint={(check.error as ApiError).hint}
              correlationId={(check.error as ApiError).correlationId}
              onRetry={submit}
            />
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------ result */}
      {result && (
        <motion.div
          key={`${result.mission_id}-${result.correct}-${result.score}`}
          initial={reducedMotion ? false : { opacity: 0, scale: 0.985 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          role="status"
          aria-live="polite"
          className={cx(
            "mt-4 rounded-[var(--radius-md)] border p-4",
            result.correct
              ? "border-[color-mix(in_oklab,var(--color-ok)_42%,transparent)] bg-[color-mix(in_oklab,var(--color-ok)_10%,transparent)]"
              : "border-[color-mix(in_oklab,var(--color-degraded)_42%,transparent)] bg-[color-mix(in_oklab,var(--color-degraded)_8%,transparent)]",
          )}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p
              className={cx(
                "flex items-center gap-2 text-[14px] font-semibold",
                result.correct ? "text-[var(--color-ok)]" : "text-[var(--color-degraded)]",
              )}
            >
              {result.correct ? (
                <CheckCircle2 size={16} aria-hidden />
              ) : (
                <XCircle size={16} aria-hidden />
              )}
              {result.correct ? "Correct" : "Not yet"}
            </p>
            <p className="numeral text-[13px] text-[var(--color-ink-2)]">
              {result.score} / {result.max_score} points
            </p>
          </div>

          <p className="mt-2 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
            {result.message}
          </p>

          {result.correct && result.teaches && (
            <div className="mt-3 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3 py-2.5">
              <p className="label-eyebrow">What this teaches</p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
                {result.teaches}
              </p>
            </div>
          )}

          {result.reveal.length > 0 && (
            <div className="mt-3">
              <p className="label-eyebrow">The answer</p>
              <ul className="mt-1.5 space-y-1">
                {result.reveal.map((nodeId, position) => (
                  <li key={nodeId}>
                    <button
                      onClick={() => select(nodeId)}
                      className="flex w-full flex-wrap items-baseline gap-2 rounded-[var(--radius-xs)] px-1.5 py-1 text-left transition-colors hover:bg-[var(--color-surface-2)]"
                    >
                      <span className="text-[12.5px] text-[var(--color-ink)]">
                        {result.reveal_labels[position] ?? nodeId}
                      </span>
                      <span className="mono break-all text-[10.5px] text-[var(--color-dim)]">
                        {nodeId}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            {result.correct && result.share_text && (
              <Button variant="secondary" size="sm" onClick={() => void copyResult()}>
                <Copy size={13} aria-hidden /> Copy result
              </Button>
            )}
            {!result.correct && (
              <Button variant="secondary" size="sm" onClick={() => setResult(null)}>
                Try again
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={onExit}>
              Back to missions
            </Button>
          </div>
        </motion.div>
      )}

      <div className="mt-4">
        <InfoNote>
          Missions use the live product: every identifier, finding and impact number above
          is the real one. Nothing is simplified for the game.
        </InfoNote>
      </div>
    </Card>
  );
}
