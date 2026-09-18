"use client";

/**
 * Journeys — the page where the estate stops being a diagram and starts being a story.
 *
 * Left: every journey with its step count, the services it crosses, where it came from,
 * and whether it still validates. Right: the player.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Route } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Inspector } from "@/components/workspace/inspector";
import { InspectorRail, PageHeader } from "@/components/workspace/shell";
import { JourneyList } from "@/components/journeys/journey-list";
import { JourneyPlayer } from "@/components/journeys/journey-player";
import { NewJourneyDialog } from "@/components/journeys/new-journey-dialog";
import { Button, EmptyState, ErrorState, LoadingBlock } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { Journey } from "@/lib/types";

export default function Page() {
  return (
    <React.Suspense fallback={<PageFallback />}>
      <JourneysView />
    </React.Suspense>
  );
}

function PageFallback() {
  return (
    <div className="p-5">
      <LoadingBlock label="Loading journeys" rows={5} />
    </div>
  );
}

function JourneysView() {
  const { projectId } = useParams<{ projectId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const scenarioId = useWorkspace((s) => s.activeScenarioId);
  const toast = useWorkspace((s) => s.toast);
  const queryClient = useQueryClient();

  const requested = searchParams.get("journey");
  const [selectedId, setSelectedId] = React.useState<string | null>(requested);
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const journeys = useQuery({
    queryKey: ["journeys", projectId, scenarioId],
    queryFn: () => api.journeys(projectId, scenarioId ?? undefined),
  });

  const list = React.useMemo(() => journeys.data?.journeys ?? [], [journeys.data]);

  // The URL wins when it names a journey that exists; otherwise fall back to the first.
  React.useEffect(() => {
    if (list.length === 0) return;
    const wanted = requested && list.some((journey) => journey.id === requested) ? requested : null;
    setSelectedId((current) => {
      if (wanted) return wanted;
      if (current && list.some((journey) => journey.id === current)) return current;
      return list[0].id;
    });
  }, [list, requested]);

  const select = (journeyId: string) => {
    setSelectedId(journeyId);
    const params = new URLSearchParams(searchParams.toString());
    params.set("journey", journeyId);
    router.replace(`/workspace/${projectId}/journeys?${params.toString()}`, { scroll: false });
  };

  const remove = useMutation({
    mutationFn: (journey: Journey) => api.deleteJourney(projectId, journey.id),
    onSuccess: async (_result, journey) => {
      await queryClient.invalidateQueries({ queryKey: ["journeys", projectId] });
      toast("success", `Deleted “${journey.name}”.`);
      setSelectedId((current) => (current === journey.id ? null : current));
    },
    onError: (error) => {
      const problem = error as ApiError;
      toast(
        "error",
        problem.correlationId
          ? `${problem.message} (correlation ID ${problem.correlationId})`
          : problem.message,
      );
    },
  });

  return (
    <>
      <div className="flex h-full min-h-0">
        <div className="flex min-w-0 flex-1 flex-col">
          <PageHeader
            icon={Route}
            title="Journeys"
            subtitle="A journey is a business flow told as a sequence of real API calls. Play one to watch it cross the estate, with the evidence for every hop."
            actions={
              <Button variant="primary" size="sm" onClick={() => setDialogOpen(true)}>
                <Plus size={13} aria-hidden /> New journey
              </Button>
            }
          />

          <div className="flex min-h-0 flex-1">
            {/* ------------------------------------------------------- the rail */}
            <aside
              className="w-[268px] shrink-0 overflow-y-auto border-r border-[var(--color-line)] 2xl:w-[310px]"
              aria-label="Journey list"
            >
              {journeys.isLoading ? (
                <div className="p-3.5">
                  <LoadingBlock label="Loading journeys" rows={6} />
                </div>
              ) : journeys.error ? (
                <div className="p-3.5">
                  <ErrorState
                    title="Journeys could not be loaded"
                    detail={(journeys.error as ApiError).message}
                    hint={(journeys.error as ApiError).hint}
                    correlationId={(journeys.error as ApiError).correlationId}
                    onRetry={() => void journeys.refetch()}
                  />
                </div>
              ) : list.length === 0 ? (
                <EmptyState
                  icon={<Route size={22} aria-hidden />}
                  title="No journeys yet"
                  body="Journeys are derived from the specifications when a flow is obvious, and composed by hand when it is not."
                  action={
                    <Button variant="secondary" size="sm" onClick={() => setDialogOpen(true)}>
                      <Plus size={13} aria-hidden /> Compose one
                    </Button>
                  }
                />
              ) : (
                <JourneyList
                  journeys={list}
                  selectedId={selectedId}
                  onSelect={select}
                  onDelete={(journey) => remove.mutate(journey)}
                  deletingId={remove.isPending ? (remove.variables?.id ?? null) : null}
                />
              )}
            </aside>

            {/* ----------------------------------------------------- the player */}
            <div className="min-w-0 flex-1 overflow-y-auto p-5">
              {selectedId ? (
                <JourneyPlayer projectId={projectId} journeyId={selectedId} />
              ) : (
                <EmptyState
                  icon={<Route size={22} aria-hidden />}
                  title="Pick a journey"
                  body="Choose a flow on the left to play it step by step across the graph."
                />
              )}
            </div>
          </div>
        </div>

        <InspectorRail>
          <Inspector projectId={projectId} />
        </InspectorRail>
      </div>

      <NewJourneyDialog
        projectId={projectId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={select}
      />
    </>
  );
}
