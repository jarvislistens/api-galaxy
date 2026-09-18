"use client";

/**
 * Missions — the guided way in.
 *
 * Each mission is a real question about this estate, answered with the real tools. The
 * scoreboard is deliberately thin and deliberately temporary: this is a teaching device,
 * not a progression system, and it says so on the page.
 */

import { useQuery } from "@tanstack/react-query";
import { Target, Trophy } from "lucide-react";
import { useParams } from "next/navigation";
import * as React from "react";
import { ActiveMission } from "@/components/missions/active-mission";
import { MissionCard } from "@/components/missions/mission-card";
import { Inspector } from "@/components/workspace/inspector";
import { InspectorRail, PageHeader } from "@/components/workspace/shell";
import {
  Card,
  EmptyState,
  ErrorState,
  InfoNote,
  LoadingBlock,
  ProgressBar,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();
  const missionId = useWorkspace((s) => s.missionId);
  const setMission = useWorkspace((s) => s.setMission);

  // Session-only. Stated as such in the UI rather than implied by its absence.
  const [solved, setSolved] = React.useState<Record<string, number>>({});

  const missions = useQuery({
    queryKey: ["missions"],
    queryFn: () => api.missions(),
    staleTime: 10 * 60 * 1000,
  });

  const list = missions.data?.missions ?? [];
  const active = list.find((mission) => mission.id === missionId) ?? null;

  const solvedCount = Object.keys(solved).length;
  const earned = Object.values(solved).reduce((total, score) => total + score, 0);
  const available = list.reduce((total, mission) => total + mission.points, 0);

  React.useEffect(() => () => setMission(null), [setMission]);

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <PageHeader
          icon={Target}
          title="Missions"
          subtitle="Five real problems in this estate, solved with the real product. Nothing here simplifies or hides what the graph actually says."
        />

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="mx-auto max-w-[1180px] space-y-4">
            {/* ---------------------------------------------- progress strip */}
            <Card className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-5">
                  <div>
                    <p className="label-eyebrow">Missions solved</p>
                    <p className="numeral mt-0.5 text-[20px] font-semibold text-[var(--color-ink)]">
                      {solvedCount}
                      <span className="text-[14px] font-normal text-[var(--color-dim)]">
                        {" "}
                        / {list.length || "—"}
                      </span>
                    </p>
                  </div>
                  <div className="h-8 w-px bg-[var(--color-line)]" aria-hidden />
                  <div>
                    <p className="label-eyebrow flex items-center gap-1.5">
                      <Trophy size={11} aria-hidden /> Points earned
                    </p>
                    <p className="numeral mt-0.5 text-[20px] font-semibold text-[var(--color-ink)]">
                      {earned}
                      <span className="text-[14px] font-normal text-[var(--color-dim)]">
                        {" "}
                        / {available || "—"}
                      </span>
                    </p>
                  </div>
                </div>
                <div className="min-w-[200px] flex-1">
                  <ProgressBar
                    value={list.length ? solvedCount / list.length : 0}
                    label={`${solvedCount} of ${list.length} missions solved`}
                  />
                  <p className="mt-2 text-[11.5px] text-[var(--color-dim)]">
                    Progress is not saved between sessions. Reload the page and this
                    scoreboard starts again — the findings you made in the graph do not.
                  </p>
                </div>
              </div>
            </Card>

            {active && (
              <ActiveMission
                key={active.id}
                projectId={projectId}
                mission={active}
                onExit={() => setMission(null)}
                onSolved={(id, score) =>
                  setSolved((current) => ({
                    ...current,
                    [id]: Math.max(current[id] ?? 0, score),
                  }))
                }
              />
            )}

            {/* ----------------------------------------------- mission cards */}
            {missions.isLoading ? (
              <Card className="p-5">
                <LoadingBlock label="Loading missions" rows={5} />
              </Card>
            ) : missions.error ? (
              <ErrorState
                title="Missions could not be loaded"
                detail={(missions.error as ApiError).message}
                hint={(missions.error as ApiError).hint}
                correlationId={(missions.error as ApiError).correlationId}
                onRetry={() => void missions.refetch()}
              />
            ) : list.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<Target size={22} aria-hidden />}
                  title="No missions are available"
                  body="The backend returned an empty mission catalogue."
                />
              </Card>
            ) : (
              <ul className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
                {list.map((mission) => (
                  <li key={mission.id}>
                    <MissionCard
                      mission={mission}
                      active={mission.id === missionId}
                      solved={mission.id in solved}
                      onStart={() => setMission(mission.id)}
                    />
                  </li>
                ))}
              </ul>
            )}

            {missions.data?.note && (
              <InfoNote>{missions.data.note}</InfoNote>
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
