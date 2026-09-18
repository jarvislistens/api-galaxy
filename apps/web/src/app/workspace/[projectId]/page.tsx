"use client";

/**
 * The overview.
 *
 * The question this page answers, in order: what is in here, how is it organised, what
 * looks wrong, how much of it should you believe, and what should you do next. Every
 * card on it is a door into the rest of the workspace — nothing here is read-only
 * decoration.
 */

import { Gauge } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { CountsStrip } from "@/components/overview/counts-strip";
import { CoverageCard } from "@/components/overview/coverage-card";
import { DerivationCard } from "@/components/overview/derivation";
import { DomainCards } from "@/components/overview/domain-cards";
import { JourneyCards } from "@/components/overview/journey-cards";
import { NextActions } from "@/components/overview/next-actions";
import { RiskList } from "@/components/overview/risk-list";
import { Badge, Card, ErrorState, LoadingBlock, Skeleton } from "@/components/ui/primitives";
import { PageHeader } from "@/components/workspace/shell";
import { api, ApiError } from "@/lib/api";
import { useWorkspace, type ZoomLevel } from "@/lib/store";

/**
 * Which semantic zoom level a node id first becomes visible at.
 *
 * The backend already stamps every node with a `zoom`, and the prefixes are stable, so
 * jumping to a finding can land on the right level instead of dumping the reader into a
 * 366-node view and letting them search for the thing they clicked.
 */
const ZOOM_BY_PREFIX: Record<string, ZoomLevel> = {
  estate: 1,
  domain: 1,
  capability: 1,
  svc: 2,
  journey: 2,
  entity: 2,
  op: 3,
  ep: 3,
  schema: 3,
  jstep: 3,
  risk: 3,
  sec: 3,
  server: 3,
  field: 4,
};

function zoomForNodeId(nodeId: string): ZoomLevel {
  return ZOOM_BY_PREFIX[nodeId.split(":")[0]] ?? 4;
}

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();
  const router = useRouter();
  const select = useWorkspace((s) => s.select);
  const setDomainFilter = useWorkspace((s) => s.setDomainFilter);
  const setServiceFilter = useWorkspace((s) => s.setServiceFilter);
  const setZoom = useWorkspace((s) => s.setZoom);

  const base = `/workspace/${projectId}`;

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["overview", projectId],
    queryFn: () => api.overview(projectId),
  });

  const openDomain = React.useCallback(
    (domainId: string) => {
      setDomainFilter(domainId);
      setServiceFilter(null);
      setZoom(2);
      router.push(`${base}/galaxy`);
    },
    [base, router, setDomainFilter, setServiceFilter, setZoom],
  );

  const openJourney = React.useCallback(
    (journeyId: string) => {
      router.push(`${base}/journeys?journey=${encodeURIComponent(journeyId)}`);
    },
    [base, router],
  );

  const openNode = React.useCallback(
    (nodeId: string) => {
      select(nodeId);
      setZoom(zoomForNodeId(nodeId));
      router.push(`${base}/galaxy`);
    },
    [base, router, select, setZoom],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        icon={Gauge}
        title={data ? data.project_name : "Overview"}
        subtitle="What is in this estate, how it is organised, what looks risky, and what to do next. Everything derived rather than read is labelled."
        actions={
          data ? (
            <Badge tone="neutral">
              <span className="numeral">{data.counts.nodes ?? 0}</span>&nbsp;nodes ·&nbsp;
              <span className="numeral">{data.counts.edges ?? 0}</span>&nbsp;relationships
            </Badge>
          ) : undefined
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1180px] space-y-6 px-5 py-5">
          {isLoading && <OverviewSkeleton />}

          {error && (
            <ErrorState
              title="Could not load this estate"
              detail={
                error instanceof ApiError
                  ? error.message
                  : "The overview request failed. The backend may not be running on port 8099."
              }
              hint={error instanceof ApiError ? error.hint : undefined}
              correlationId={error instanceof ApiError ? error.correlationId : undefined}
              onRetry={() => void refetch()}
            />
          )}

          {data && (
            <>
              <CountsStrip counts={data.counts} />

              <DerivationCard
                derivation={data.derivation}
                parseCoverage={data.parse_coverage}
                enrichment={data.enrichment}
              />

              <DomainCards domains={data.domains} onOpen={openDomain} />

              <JourneyCards journeys={data.journeys} onOpen={openJourney} />

              <RiskList
                risks={data.top_risks}
                ambiguities={data.ambiguities}
                onOpenNode={openNode}
              />

              <CoverageCard parseCoverage={data.parse_coverage} enrichment={data.enrichment} />

              <NextActions base={base} topJourneyId={data.journeys[0]?.id} />

              <p className="pb-2 text-center text-[11.5px] text-[var(--color-dim)]">
                Everything on this page was computed on this machine.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * The loading state reserves the same shape the real page occupies, so nothing jumps
 * when the data lands.
 */
function OverviewSkeleton() {
  return (
    <div className="space-y-6" aria-busy>
      <Card className="p-4">
        <LoadingBlock label="Loading this estate" rows={2} />
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4 xl:grid-cols-7">
          {Array.from({ length: 7 }).map((_, index) => (
            <div key={index} className="space-y-2">
              <Skeleton className="h-6 w-12" />
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-4">
        <Skeleton className="h-4 w-48" />
        <div className="mt-3 space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Card key={index} className="space-y-2 p-3.5">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-5 w-32" />
          </Card>
        ))}
      </div>

      <Card className="divide-y divide-[var(--color-line)]">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="space-y-2 px-4 py-3.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        ))}
      </Card>
    </div>
  );
}
