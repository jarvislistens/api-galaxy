"use client";

/**
 * Break Lab.
 *
 * Everything on this page is a statement about a graph. That is not a disclaimer bolted on
 * at the bottom — the assumptions and limitations the backend returns are rendered verbatim
 * next to the numbers they qualify, because a blast radius without its assumptions is a
 * prediction, and this is not one.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FlaskConical,
  History,
  Info,
  ShieldAlert,
  Undo2,
} from "lucide-react";
import * as React from "react";
import { ChangeBuilder, type ChangeKind } from "@/components/break-lab/change-builder";
import { ComparePanel, type ComparePayload } from "@/components/break-lab/compare-panel";
import { ImpactGraph } from "@/components/break-lab/impact-graph";
import { JourneysPanel } from "@/components/break-lab/journeys-panel";
import { PatchPanel } from "@/components/break-lab/patch-panel";
import { ChangeSummaryPanel, RepairsPanel } from "@/components/break-lab/repairs-panel";
import { ImpactCounts, ShockwaveTable, normaliseItem } from "@/components/break-lab/shockwave";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingBlock,
  SectionTitle,
  Tab,
  TabPanel,
  Tabs,
  TabsBar,
} from "@/components/ui/primitives";
import { Inspector } from "@/components/workspace/inspector";
import { InspectorRail, PageHeader } from "@/components/workspace/shell";
import { ScenarioBar } from "@/components/break-lab/scenario-bar";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { ImpactPayload, Scenario } from "@/lib/types";

const STANDING_NOTE =
  "This is a statement about the specification graph, not a prediction about production.";

export function BreakLab({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const scenarioId = useWorkspace((s) => s.activeScenarioId);
  const setScenario = useWorkspace((s) => s.setScenario);
  const select = useWorkspace((s) => s.select);
  const selectedNodeId = useWorkspace((s) => s.selectedNodeId);
  const setHighlight = useWorkspace((s) => s.setHighlight);
  const toast = useWorkspace((s) => s.toast);
  const pushUndo = useWorkspace((s) => s.pushUndo);

  const [tab, setTab] = React.useState("impact");
  const [pulse, setPulse] = React.useState("initial");

  /* ----------------------------------------------------------------- queries */

  const scenarios = useQuery({
    queryKey: ["scenarios", projectId],
    queryFn: () => api.scenarios(projectId),
  });

  const kinds = useQuery({
    queryKey: ["change-kinds", projectId],
    queryFn: () => api.changeKinds(projectId),
    staleTime: Infinity,
  });

  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.providers(),
  });

  const impact = useQuery<ImpactPayload>({
    queryKey: ["impact", projectId, scenarioId],
    queryFn: () => api.impact(projectId, scenarioId!),
    enabled: Boolean(scenarioId),
  });

  const graph = useQuery({
    queryKey: ["graph", projectId, "break-lab", scenarioId],
    queryFn: () =>
      api.graph(projectId, { level: 3, scenario: scenarioId ?? undefined, max_nodes: 800 }),
    enabled: Boolean(scenarioId),
  });

  const compare = useQuery<ComparePayload>({
    queryKey: ["compare", projectId, scenarioId],
    queryFn: () => api.compare(projectId, scenarioId!),
    enabled: Boolean(scenarioId) && tab === "compare",
  });

  const summary = useQuery({
    queryKey: ["change-summary", projectId, scenarioId],
    queryFn: () => api.changeSummary(projectId, scenarioId!),
    enabled: Boolean(scenarioId) && tab === "repairs",
  });

  const refreshAll = React.useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["impact", projectId] });
    queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
    queryClient.invalidateQueries({ queryKey: ["scenarios", projectId] });
    queryClient.invalidateQueries({ queryKey: ["compare", projectId] });
    queryClient.invalidateQueries({ queryKey: ["change-summary", projectId] });
    queryClient.invalidateQueries({ queryKey: ["scenario-patch", projectId] });
  }, [queryClient, projectId]);

  /* --------------------------------------------------------------- mutations */

  const createScenario = useMutation({
    mutationFn: ({ name, description }: { name: string; description: string }) =>
      api.createScenario(projectId, name, description),
    onSuccess: (payload) => {
      setScenario(payload.scenario.id);
      queryClient.invalidateQueries({ queryKey: ["scenarios", projectId] });
      toast("success", `Scenario "${payload.scenario.name}" created. The base project is untouched.`);
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not create the scenario."),
  });

  const addChange = useMutation({
    mutationFn: (body: { kind: string; target_id: string; params: Record<string, any>; label: string }) =>
      api.addChange(projectId, scenarioId!, body),
    onSuccess: (payload) => {
      queryClient.setQueryData(["impact", projectId, scenarioId], payload);
      refreshAll();
      setPulse(`${Date.now()}`);
      setHighlight({
        nodes: payload.shockwave.map((item) => item.node_id),
        reason: "Impacted by the latest change",
      });
      const index = payload.scenario.changes.length - 1;
      pushUndo({
        label: `Change: ${payload.scenario.changes[index]?.label ?? "untitled"}`,
        undo: async () => {
          await api.undoChange(projectId, scenarioId!, index);
          refreshAll();
        },
        redo: async () => {
          await api.addChange(projectId, scenarioId!, {
            kind: payload.scenario.changes[index].kind,
            target_id: payload.scenario.changes[index].target_id,
            params: payload.scenario.changes[index].params,
          });
          refreshAll();
        },
      });
      const counts = payload.impact.counts;
      toast(
        counts.broken ? "warning" : "success",
        `${counts.broken ?? 0} broken, ${counts.degraded ?? 0} degraded, ${
          counts.potentially_affected ?? 0
        } potentially affected.`,
      );
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not apply that change."),
  });

  const undoChange = useMutation({
    mutationFn: (index: number) => api.undoChange(projectId, scenarioId!, index),
    onSuccess: (payload) => {
      queryClient.setQueryData(["impact", projectId, scenarioId], payload);
      refreshAll();
      setPulse(`${Date.now()}`);
      toast("info", "Change undone.");
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not undo that change."),
  });

  const resetScenario = useMutation({
    mutationFn: () => api.resetScenario(projectId, scenarioId!),
    onSuccess: (payload) => {
      queryClient.setQueryData(["impact", projectId, scenarioId], payload);
      refreshAll();
      setPulse(`${Date.now()}`);
      toast("success", "Scenario reset. Every change and applied repair has been removed.");
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not reset the scenario."),
  });

  const deleteScenario = useMutation({
    mutationFn: () => api.deleteScenario(projectId, scenarioId!),
    onSuccess: () => {
      setScenario(null);
      refreshAll();
      toast("success", "Scenario deleted. The imported project is unchanged.");
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not delete the scenario."),
  });

  /* ------------------------------------------------------------------ derived */

  const scenarioList: Scenario[] = React.useMemo(
    () => scenarios.data?.scenarios ?? [],
    [scenarios.data],
  );
  const activeScenario = impact.data?.scenario ?? scenarioList.find((s) => s.id === scenarioId) ?? null;
  const shockwave = React.useMemo(
    () => (impact.data?.shockwave ?? []).map(normaliseItem),
    [impact.data],
  );
  const impactMap = React.useMemo(
    () => Object.fromEntries(shockwave.map((item) => [item.node_id, item.status])),
    [shockwave],
  );
  const counts = impact.data?.impact.counts ?? {};
  const changes = activeScenario?.changes ?? [];
  const busy =
    addChange.isPending || undoChange.isPending || resetScenario.isPending || deleteScenario.isPending;

  // A scenario that was deleted elsewhere should not stay "active" in the store.
  //
  // The guard is `isFetching`, not `isLoading`. `isLoading` is only true on the very
  // first fetch, so after creating a scenario this effect ran against the *stale* list —
  // which of course did not contain the scenario that had just been created — and
  // immediately cleared it. Creating a scenario looked like it silently did nothing,
  // even though the API had stored it correctly.
  React.useEffect(() => {
    if (!scenarioId || scenarios.isFetching) return;
    if (!scenarioList.some((scenario) => scenario.id === scenarioId)) setScenario(null);
  }, [scenarioId, scenarioList, scenarios.isFetching, setScenario]);

  /* --------------------------------------------------------------------- view */

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <PageHeader
          icon={FlaskConical}
          title="Break Lab"
          subtitle="Simulate a breaking change and see exactly what stops working, why, and which business journeys go down with it."
          actions={
            <Badge tone="fact">Deterministic · same input, same blast radius</Badge>
          }
        />

        <ScenarioBar
          scenarios={scenarioList}
          activeId={scenarioId}
          onSelect={setScenario}
          onCreate={(name, description) => createScenario.mutate({ name, description })}
          onReset={() => resetScenario.mutate()}
          onDelete={() => deleteScenario.mutate()}
          busy={busy}
          creating={createScenario.isPending}
        />

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="px-5 py-5">
            {scenarios.isLoading ? (
              <Card className="p-5">
                <LoadingBlock rows={4} label="Loading scenarios" />
              </Card>
            ) : scenarios.error ? (
              <ErrorState
                title="Could not load scenarios"
                detail={
                  scenarios.error instanceof ApiError
                    ? scenarios.error.message
                    : String(scenarios.error)
                }
                correlationId={
                  scenarios.error instanceof ApiError ? scenarios.error.correlationId : undefined
                }
                onRetry={() => scenarios.refetch()}
              />
            ) : !scenarioId ? (
              <Card className="p-5">
                <EmptyState
                  icon={<FlaskConical size={22} aria-hidden />}
                  title="Pick a scenario, or make one"
                  body="A scenario is a named clone of your graph. Changes are applied to the clone and computed by traversal — the imported specification is never modified, so nothing here can damage it."
                />
              </Card>
            ) : (
              <Tabs value={tab} onValueChange={setTab}>
                <TabsBar aria-label="Break Lab sections" className="mb-5 w-fit">
                  <Tab value="impact">Impact</Tab>
                  <Tab value="repairs">Repair</Tab>
                  <Tab value="compare">Before / after</Tab>
                </TabsBar>

                {/* ------------------------------------------------- impact */}
                <TabPanel value="impact" className="space-y-5 focus-visible:outline-none">
                  <div className="grid gap-5 2xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
                    <div className="space-y-5">
                      <ChangeBuilder
                        projectId={projectId}
                        kinds={(kinds.data?.kinds ?? []) as ChangeKind[]}
                        onSubmit={(draft) => addChange.mutate(draft)}
                        disabled={busy}
                        pending={addChange.isPending}
                      />
                      <ChangeList
                        changes={changes}
                        onUndo={(index) => undoChange.mutate(index)}
                        busy={busy}
                      />
                    </div>

                    <div className="min-w-0 space-y-5">
                      {impact.isLoading ? (
                        <Card className="p-5">
                          <LoadingBlock rows={5} label="Computing impact" />
                        </Card>
                      ) : impact.error ? (
                        <ErrorState
                          title="Could not compute impact"
                          detail={
                            impact.error instanceof ApiError
                              ? impact.error.message
                              : String(impact.error)
                          }
                          correlationId={
                            impact.error instanceof ApiError
                              ? impact.error.correlationId
                              : undefined
                          }
                          onRetry={() => impact.refetch()}
                        />
                      ) : (
                        <div aria-live="polite" className="space-y-5">
                          <ImpactCounts counts={counts} pulseKey={pulse} />

                          <p className="flex items-start gap-2 text-[12px] leading-snug text-[var(--color-muted)]">
                            <Info size={13} className="mt-[2px] shrink-0 text-[var(--color-dim)]" aria-hidden />
                            <span>
                              <span className="numeral">{counts.journeys_broken ?? 0}</span> of{" "}
                              <span className="numeral">{counts.journeys_total ?? 0}</span> journeys
                              are broken. {STANDING_NOTE}
                            </span>
                          </p>

                          <ImpactGraph
                            graph={graph.data}
                            impact={impactMap}
                            selectedId={selectedNodeId}
                            onSelect={select}
                            loading={graph.isLoading}
                          />

                          <Card className="p-5">
                            <SectionTitle>Shockwave</SectionTitle>
                            <ShockwaveTable
                              items={shockwave}
                              onSelect={select}
                              selectedId={selectedNodeId}
                            />
                          </Card>

                          <JourneysPanel
                            affected={impact.data?.journeys ?? []}
                            all={impact.data?.all_journeys ?? []}
                          />

                          <AssumptionsPanel
                            assumptions={impact.data?.impact.assumptions ?? []}
                            limitations={impact.data?.impact.limitations ?? []}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                </TabPanel>

                {/* ------------------------------------------------ repairs */}
                <TabPanel value="repairs" className="focus-visible:outline-none">
                  <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
                    <div className="min-w-0">
                      <RepairsPanel
                        projectId={projectId}
                        scenarioId={scenarioId}
                        providers={providers.data?.providers ?? []}
                        hasChanges={changes.length > 0}
                        onChanged={refreshAll}
                      />
                    </div>
                    <div className="space-y-5">
                      <PatchPanel
                        projectId={projectId}
                        scenarioId={scenarioId}
                        hasChanges={changes.length > 0}
                      />
                      <ChangeSummaryPanel
                        markdown={summary.data?.markdown ?? ""}
                        patch={summary.data?.patch ?? []}
                        migrationSteps={summary.data?.migration_steps ?? []}
                        loading={summary.isLoading}
                      />
                      <AssumptionsPanel
                        assumptions={impact.data?.impact.assumptions ?? []}
                        limitations={impact.data?.impact.limitations ?? []}
                      />
                    </div>
                  </div>
                </TabPanel>

                {/* ------------------------------------------------ compare */}
                <TabPanel value="compare" className="focus-visible:outline-none">
                  {compare.isLoading ? (
                    <Card className="p-5">
                      <LoadingBlock rows={5} label="Comparing before and after" />
                    </Card>
                  ) : compare.error ? (
                    <ErrorState
                      title="Could not compare"
                      detail={
                        compare.error instanceof ApiError
                          ? compare.error.message
                          : String(compare.error)
                      }
                      correlationId={
                        compare.error instanceof ApiError ? compare.error.correlationId : undefined
                      }
                      onRetry={() => compare.refetch()}
                    />
                  ) : (
                    <ComparePanel data={compare.data ?? null} />
                  )}
                </TabPanel>
              </Tabs>
            )}
          </div>
        </div>
      </div>

      <InspectorRail>
        <Inspector projectId={projectId} />
      </InspectorRail>
    </div>
  );
}

/* --------------------------------------------------------------- change list */

function ChangeList({
  changes,
  onUndo,
  busy,
}: {
  changes: { id: string; kind: string; target_id: string; label: string; params: Record<string, any> }[];
  onUndo: (index: number) => void;
  busy?: boolean;
}) {
  return (
    <Card className="p-5">
      <SectionTitle>
        <span className="flex items-center gap-1.5">
          <History size={13} className="text-[var(--color-dim)]" aria-hidden />
          Changes in this scenario
        </span>
      </SectionTitle>
      {changes.length === 0 ? (
        <p className="text-[12.5px] text-[var(--color-dim)]">
          None yet. Nothing has been changed, so nothing is broken.
        </p>
      ) : (
        <ol className="space-y-2">
          {changes.map((change, index) => (
            <li
              key={change.id}
              className="flex items-start justify-between gap-3 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="text-[12.5px] text-[var(--color-ink)]">{change.label}</p>
                <p className="mono mt-0.5 truncate text-[11px] text-[var(--color-dim)]">
                  {change.kind} · {change.target_id}
                </p>
                {Object.keys(change.params ?? {}).length > 0 && (
                  <p className="mono mt-0.5 text-[11px] text-[var(--color-muted)]">
                    {Object.entries(change.params)
                      .map(([key, value]) => `${key}=${String(value)}`)
                      .join("  ")}
                  </p>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onUndo(index)}
                disabled={busy}
                aria-label={`Undo change ${index + 1}: ${change.label}`}
              >
                <Undo2 size={13} aria-hidden />
                Undo
              </Button>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

/* -------------------------------------------------- assumptions/limitations */

function AssumptionsPanel({
  assumptions,
  limitations,
}: {
  assumptions: string[];
  limitations: string[];
}) {
  return (
    <Card className="p-5">
      <SectionTitle>
        <span className="flex items-center gap-1.5">
          <ShieldAlert size={13} className="text-[var(--color-degraded)]" aria-hidden />
          Assumptions and limitations
        </span>
      </SectionTitle>

      <p className="mb-4 text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
        {STANDING_NOTE}
      </p>

      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <p className="label-eyebrow mb-1.5">What this analysis assumes</p>
          {assumptions.length ? (
            <ul className="space-y-1.5">
              {assumptions.map((line) => (
                <li key={line} className="text-[12.5px] leading-snug text-[var(--color-muted)]">
                  {line}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12.5px] text-[var(--color-dim)]">
              The backend returned no assumptions for this scenario.
            </p>
          )}
        </div>
        <div>
          <p className="label-eyebrow mb-1.5">What it cannot see</p>
          {limitations.length ? (
            <ul className="space-y-1.5">
              {limitations.map((line) => (
                <li key={line} className="text-[12.5px] leading-snug text-[var(--color-muted)]">
                  {line}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12.5px] text-[var(--color-dim)]">
              The backend returned no limitations for this scenario.
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
