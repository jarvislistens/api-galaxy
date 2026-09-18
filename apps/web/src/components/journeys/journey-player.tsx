"use client";

/**
 * The journey player.
 *
 * A journey is the one artefact in this product that is genuinely temporal, so it gets a
 * transport: play, pause, step, restart, speed. Three rules shape it.
 *
 * 1. **The graph is the picture, the prose is the caption.** Every frame drives the shared
 *    highlight store *and* a local canvas showing only this journey's subgraph, so the
 *    traversal is visible rather than described.
 * 2. **Plain language first, technical detail second, evidence third.** In that order,
 *    always, because that is the order a reader needs them in.
 * 3. **Reduced motion means no motion.** With the OS preference set, Play advances one
 *    step instantly instead of running a timer. Nothing becomes unreachable.
 */

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileCode2,
  Pause,
  Play,
  RotateCcw,
} from "lucide-react";
import * as React from "react";
import { GraphCanvas, GraphNodeList } from "@/components/graph/graph-canvas";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  InfoNote,
  LoadingBlock,
  SectionTitle,
  Tooltip,
  cx,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { GraphEdge, GraphNode, PlaybackFrame } from "@/lib/types";

/** Base dwell per frame. Long enough to read a sentence, short enough to keep moving. */
const BASE_DWELL_MS = 2600;
const SPEEDS = [0.5, 1, 1.5, 2] as const;
type Speed = (typeof SPEEDS)[number];

function useReducedMotion() {
  const [reduced, setReduced] = React.useState(false);
  React.useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/** Narrow a full graph down to the nodes a journey actually touches, plus their edges. */
function subgraphFor(
  nodes: GraphNode[],
  edges: GraphEdge[],
  frames: PlaybackFrame[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const wanted = new Set<string>();
  for (const frame of frames) {
    for (const id of frame.highlight_nodes) wanted.add(id);
    for (const id of frame.trail) wanted.add(id);
  }
  const keptNodes = nodes.filter((node) => wanted.has(node.id));
  const present = new Set(keptNodes.map((node) => node.id));
  const keptEdges = edges.filter(
    (edge) => present.has(edge.source) && present.has(edge.target),
  );
  return { nodes: keptNodes, edges: keptEdges };
}

export function JourneyPlayer({
  projectId,
  journeyId,
}: {
  projectId: string;
  journeyId: string;
}) {
  const scenarioId = useWorkspace((s) => s.activeScenarioId);
  const setHighlight = useWorkspace((s) => s.setHighlight);
  const clearHighlight = useWorkspace((s) => s.clearHighlight);
  const select = useWorkspace((s) => s.select);
  const toast = useWorkspace((s) => s.toast);
  const reducedMotion = useReducedMotion();

  const [index, setIndex] = React.useState(0);
  const [playing, setPlaying] = React.useState(false);
  const [speed, setSpeed] = React.useState<Speed>(1);
  const [exporting, setExporting] = React.useState<string | null>(null);

  const playback = useQuery({
    queryKey: ["playback", projectId, journeyId, scenarioId],
    queryFn: () => api.playback(projectId, journeyId, scenarioId ?? undefined),
  });

  // The full graph is fetched once per project and reused for every journey; the subgraph
  // is a pure filter over it, so switching journeys costs no network.
  const graph = useQuery({
    queryKey: ["graph-l3", projectId, scenarioId],
    queryFn: () =>
      api.graph(projectId, { level: 3, max_nodes: 600, scenario: scenarioId ?? undefined }),
    staleTime: 5 * 60 * 1000,
  });

  const frames = React.useMemo(() => playback.data?.frames ?? [], [playback.data]);
  const frame: PlaybackFrame | undefined = frames[index];

  // A new journey always starts at the beginning and paused.
  React.useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [journeyId, scenarioId]);

  // Drive the shared highlight so the inspector and any other canvas follow along.
  React.useEffect(() => {
    if (!frame) return;
    setHighlight({
      nodes: frame.highlight_nodes,
      edges: frame.highlight_edges,
      path: frame.trail,
      reason: `${playback.data?.journey.name ?? "Journey"} · step ${frame.order}: ${frame.label}`,
    });
  }, [frame, setHighlight, playback.data?.journey.name]);

  React.useEffect(() => () => clearHighlight(), [clearHighlight]);

  // The transport. One timeout per frame rather than a free-running interval, so speed
  // changes take effect on the next frame instead of mid-flight.
  React.useEffect(() => {
    if (!playing || reducedMotion || frames.length === 0) return;
    if (index >= frames.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(
      () => setIndex((current) => Math.min(current + 1, frames.length - 1)),
      BASE_DWELL_MS / speed,
    );
    return () => window.clearTimeout(timer);
  }, [playing, index, speed, frames.length, reducedMotion]);

  const subgraph = React.useMemo(() => {
    if (!graph.data || frames.length === 0) return { nodes: [], edges: [] };
    return subgraphFor(graph.data.nodes, graph.data.edges, frames);
  }, [graph.data, frames]);

  const atEnd = index >= frames.length - 1;

  const togglePlay = () => {
    if (reducedMotion) {
      // No timers when the reader has asked for less motion: Play is a single step.
      setIndex((current) => (current >= frames.length - 1 ? 0 : current + 1));
      return;
    }
    if (atEnd && !playing) {
      setIndex(0);
      setPlaying(true);
      return;
    }
    setPlaying((value) => !value);
  };

  const runExport = async (format: "svg" | "mermaid") => {
    setExporting(format);
    try {
      const result = await api.createExport(projectId, { format, journey_id: journeyId });
      const anchor = document.createElement("a");
      anchor.href = result.download_url;
      anchor.download = result.export.filename;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      toast("success", `Exported ${result.export.filename}`);
    } catch (error) {
      const problem = error as ApiError;
      toast(
        "error",
        problem.correlationId
          ? `Export failed: ${problem.message} (correlation ID ${problem.correlationId})`
          : `Export failed: ${problem.message}`,
      );
    } finally {
      setExporting(null);
    }
  };

  if (playback.isLoading) {
    return (
      <Card className="p-5">
        <LoadingBlock label="Loading the journey playback" rows={6} />
      </Card>
    );
  }

  if (playback.error) {
    const problem = playback.error as ApiError;
    return (
      <ErrorState
        title="This journey could not be played"
        detail={problem.message}
        hint={problem.hint}
        correlationId={problem.correlationId}
        onRetry={() => void playback.refetch()}
      />
    );
  }

  if (!playback.data || frames.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-[13px] text-[var(--color-muted)]">
          This journey has no steps to play.
        </p>
      </Card>
    );
  }

  const { journey, validation } = playback.data;
  const brokenCount = validation.broken_steps.length;

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------ header */}
      <div>
        <p className="label-eyebrow">Journey</p>
        <h3 className="mt-1 text-[18px] font-semibold tracking-tight text-[var(--color-ink)]">
          {journey.name}
        </h3>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-[var(--color-muted)]">
          {journey.description}
        </p>
        <p className="mt-2 text-[12px] text-[var(--color-dim)]">{journey.explanation}</p>
      </div>

      {/* A persistent bar, not a toast: a broken journey is a standing fact, not an event. */}
      {!validation.ok && (
        <div
          role="status"
          className="flex items-start gap-2.5 rounded-[var(--radius-md)] border border-[color-mix(in_oklab,var(--color-broken)_38%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_10%,transparent)] px-3.5 py-3"
        >
          <AlertTriangle
            size={15}
            className="mt-[2px] shrink-0 text-[var(--color-broken)]"
            aria-hidden
          />
          <div>
            <p className="text-[12.5px] font-semibold text-[var(--color-broken)]">
              {brokenCount} of {frames.length} steps no longer validate
            </p>
            <p className="mt-0.5 text-[12.5px] text-[var(--color-ink-2)]">{validation.summary}</p>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------- transport */}
      <Card className="p-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <Tooltip label="Back to step 1">
            <Button
              variant="ghost"
              size="sm"
              aria-label="Restart the journey"
              onClick={() => {
                setIndex(0);
                setPlaying(false);
              }}
            >
              <RotateCcw size={14} aria-hidden />
            </Button>
          </Tooltip>
          <Tooltip label="Previous step">
            <Button
              variant="ghost"
              size="sm"
              aria-label="Previous step"
              disabled={index === 0}
              onClick={() => {
                setPlaying(false);
                setIndex((current) => Math.max(0, current - 1));
              }}
            >
              <ChevronLeft size={15} aria-hidden />
            </Button>
          </Tooltip>

          <Button
            variant="primary"
            size="sm"
            onClick={togglePlay}
            aria-label={
              reducedMotion
                ? "Advance one step"
                : playing
                  ? "Pause playback"
                  : atEnd
                    ? "Replay from the first step"
                    : "Play the journey"
            }
          >
            {playing && !reducedMotion ? (
              <>
                <Pause size={14} aria-hidden /> Pause
              </>
            ) : (
              <>
                <Play size={14} aria-hidden />{" "}
                {reducedMotion ? "Advance" : atEnd ? "Replay" : "Play"}
              </>
            )}
          </Button>

          <Tooltip label="Next step">
            <Button
              variant="ghost"
              size="sm"
              aria-label="Next step"
              disabled={atEnd}
              onClick={() => {
                setPlaying(false);
                setIndex((current) => Math.min(frames.length - 1, current + 1));
              }}
            >
              <ChevronRight size={15} aria-hidden />
            </Button>
          </Tooltip>

          <div
            className="ml-1 flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-line)] p-0.5"
            role="group"
            aria-label="Playback speed"
          >
            {SPEEDS.map((value) => (
              <button
                key={value}
                onClick={() => setSpeed(value)}
                aria-pressed={speed === value}
                className={cx(
                  "numeral rounded-[var(--radius-xs)] px-2 py-1 text-[11.5px] transition-colors duration-150",
                  speed === value
                    ? "bg-[var(--color-surface-3)] text-[var(--color-ink)]"
                    : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
                )}
              >
                {value}×
              </button>
            ))}
          </div>

          <span className="numeral ml-1 text-[12px] text-[var(--color-dim)]">
            Step {index + 1} of {frames.length}
          </span>

          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              loading={exporting === "svg"}
              onClick={() => void runExport("svg")}
            >
              <Download size={13} aria-hidden /> SVG
            </Button>
            <Button
              variant="secondary"
              size="sm"
              loading={exporting === "mermaid"}
              onClick={() => void runExport("mermaid")}
            >
              <Download size={13} aria-hidden /> Mermaid
            </Button>
          </div>
        </div>

        {reducedMotion && (
          <div className="mt-2.5">
            <InfoNote>
              Your system asks for reduced motion, so playback does not run on a timer.
              Advance, Next and the step timeline all still work.
            </InfoNote>
          </div>
        )}

        {/* ------------------------------------------------------- timeline */}
        <ol
          className="scroll-x mt-3.5 flex items-stretch gap-1.5 pb-1"
          aria-label="Journey steps"
        >
          {frames.map((item, position) => {
            const current = position === index;
            const failed = !item.ok;
            return (
              <li key={item.step_id} className="min-w-0 flex-1">
                <Tooltip
                  label={
                    <span>
                      <span className="block font-medium text-[var(--color-ink)]">
                        Step {item.order}: {item.label}
                      </span>
                      {failed && item.problems.length > 0 && (
                        <span className="mt-1 block text-[var(--color-broken)]">
                          {item.problems.join(" ")}
                        </span>
                      )}
                      {item.deprecated && (
                        <span className="mt-1 block text-[var(--color-degraded)]">
                          Calls a deprecated operation.
                        </span>
                      )}
                    </span>
                  }
                >
                  <button
                    onClick={() => {
                      setPlaying(false);
                      setIndex(position);
                    }}
                    aria-current={current ? "step" : undefined}
                    aria-label={`Step ${item.order}: ${item.label}${failed ? " — broken" : ""}`}
                    className={cx(
                      "flex w-full min-w-[54px] flex-col items-center gap-1 rounded-[var(--radius-sm)] border px-1.5 py-1.5",
                      "transition-colors duration-150",
                      current
                        ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_16%,transparent)]"
                        : failed
                          ? "border-[color-mix(in_oklab,var(--color-broken)_42%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_10%,transparent)] hover:bg-[color-mix(in_oklab,var(--color-broken)_18%,transparent)]"
                          : "border-[var(--color-line)] hover:bg-[var(--color-surface-2)]",
                    )}
                  >
                    <span className="flex items-center gap-1">
                      {failed ? (
                        <AlertTriangle size={11} className="text-[var(--color-broken)]" aria-hidden />
                      ) : (
                        <CheckCircle2 size={11} className="text-[var(--color-ok)]" aria-hidden />
                      )}
                      <span
                        className={cx(
                          "numeral text-[11.5px] font-medium",
                          current ? "text-[var(--color-ink)]" : "text-[var(--color-ink-2)]",
                        )}
                      >
                        {item.order}
                      </span>
                    </span>
                    <span className="mono w-full truncate text-center text-[9.5px] uppercase tracking-wide text-[var(--color-dim)]">
                      {item.method ?? "step"}
                    </span>
                  </button>
                </Tooltip>
              </li>
            );
          })}
        </ol>
      </Card>

      {frame && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.85fr)]">
          {/* ------------------------------------------------- narration side */}
          <div className="space-y-4">
            <Card className="p-4" aria-live="polite">
              <p className="label-eyebrow">
                Step {frame.order} of {frames.length} — in plain language
              </p>
              <p className="mt-2 text-[16px] font-medium leading-relaxed tracking-tight text-[var(--color-ink)]">
                {frame.narration}
              </p>
              <p className="mt-2 text-[13px] text-[var(--color-muted)]">{frame.label}</p>

              {frame.deprecated && (
                <div className="mt-3 flex items-start gap-2 rounded-[var(--radius-sm)] border border-[color-mix(in_oklab,var(--color-degraded)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-degraded)_10%,transparent)] px-3 py-2">
                  <AlertTriangle
                    size={14}
                    className="mt-[2px] shrink-0 text-[var(--color-degraded)]"
                    aria-hidden
                  />
                  <p className="text-[12.5px] text-[var(--color-ink-2)]">
                    This step calls a deprecated operation. It still works today, but the
                    owning service has announced it is going away.
                  </p>
                </div>
              )}

              {!frame.ok && frame.problems.length > 0 && (
                <div className="mt-3 rounded-[var(--radius-sm)] border border-[color-mix(in_oklab,var(--color-broken)_40%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_10%,transparent)] px-3 py-2">
                  <p className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--color-broken)]">
                    <AlertTriangle size={13} aria-hidden /> This step is broken
                  </p>
                  <ul className="mt-1 space-y-0.5">
                    {frame.problems.map((problem) => (
                      <li key={problem} className="text-[12.5px] text-[var(--color-ink-2)]">
                        {problem}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>

            <Card className="p-4">
              <SectionTitle>Technical detail</SectionTitle>
              <div className="flex flex-wrap items-center gap-2">
                {frame.method && (
                  <Badge tone="accent" className="mono uppercase">
                    {frame.method}
                  </Badge>
                )}
                {frame.path && (
                  <code className="mono text-[12px] text-[var(--color-ink)]">{frame.path}</code>
                )}
                {frame.service && (
                  <Badge tone="neutral">{frame.service}</Badge>
                )}
              </div>
              <p className="mt-2.5 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
                {frame.technical_detail}
              </p>
              {frame.schemas.length > 0 && (
                <div className="mt-3">
                  <p className="label-eyebrow">Schemas on the wire</p>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5">
                    {frame.schemas.map((schema, position) => {
                      const nodeId = frame.schema_ids[position];
                      return (
                        <li key={`${schema}-${position}`}>
                          <button
                            onClick={() => nodeId && select(nodeId)}
                            className="mono rounded-[var(--radius-xs)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2 py-1 text-[11px] text-[var(--color-ink-2)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
                          >
                            {schema}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              {frame.operation_id && (
                <button
                  onClick={() => select(frame.operation_id!)}
                  className="mono mt-3 block max-w-full truncate text-left text-[11px] text-[var(--color-dim)] underline decoration-dotted underline-offset-2 transition-colors hover:text-[var(--color-accent-soft)]"
                >
                  {frame.operation_id}
                </button>
              )}
            </Card>

            <Card className="p-4">
              <SectionTitle>Evidence for this step</SectionTitle>
              {frame.evidence.length === 0 ? (
                <p className="text-[12.5px] text-[var(--color-dim)]">
                  No file locator was recorded for this step.
                </p>
              ) : (
                <ul className="space-y-2">
                  {frame.evidence.map((item) => (
                    <li
                      key={item.id}
                      className="rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3 py-2"
                    >
                      <p className="flex items-center gap-1.5 text-[12px] text-[var(--color-ink-2)]">
                        <FileCode2 size={12} className="text-[var(--color-dim)]" aria-hidden />
                        {item.label}
                      </p>
                      <p className="mono mt-1 break-all text-[11px] text-[var(--color-muted)]">
                        {item.source_file}
                        <span className="text-[var(--color-dim)]">{item.pointer}</span>
                      </p>
                      {item.excerpt && (
                        <p className="mt-1 text-[11.5px] italic text-[var(--color-dim)]">
                          “{item.excerpt}”
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {/* ----------------------------------------------------- graph side */}
          <div className="space-y-3">
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between gap-2 border-b border-[var(--color-line)] px-3.5 py-2.5">
                <p className="label-eyebrow">This journey on the graph</p>
                <span className="numeral text-[11px] text-[var(--color-dim)]">
                  {subgraph.nodes.length} nodes
                </span>
              </div>
              {graph.isLoading ? (
                <div className="p-4">
                  <LoadingBlock label="Loading the graph" rows={4} />
                </div>
              ) : graph.error ? (
                <div className="p-4">
                  <ErrorState
                    title="The graph could not be loaded"
                    detail={(graph.error as ApiError).message}
                    correlationId={(graph.error as ApiError).correlationId}
                    onRetry={() => void graph.refetch()}
                  />
                </div>
              ) : (
                <GraphCanvas
                  nodes={subgraph.nodes}
                  edges={subgraph.edges}
                  activeNodes={frame.highlight_nodes}
                  pathNodes={frame.trail}
                  highlightEdges={frame.highlight_edges}
                  onSelectNode={(nodeId) => nodeId && select(nodeId)}
                  layout="force"
                  className="h-[320px] w-full"
                  ariaLabel={`The subgraph for ${journey.name}. Step ${frame.order} of ${frames.length}, ${frame.label}, is highlighted. The list below is the keyboard equivalent.`}
                />
              )}
            </Card>

            <Card className="overflow-hidden">
              <div className="border-b border-[var(--color-line)] px-3.5 py-2.5">
                <p className="label-eyebrow">Nodes touched at this step</p>
              </div>
              <div className="max-h-[260px] overflow-y-auto">
                <GraphNodeList
                  nodes={subgraph.nodes.filter((node) =>
                    frame.highlight_nodes.includes(node.id),
                  )}
                  onSelect={select}
                  emptyLabel="This step touches no nodes that exist in the current graph level."
                />
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
