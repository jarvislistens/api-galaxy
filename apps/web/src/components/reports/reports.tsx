"use client";

/**
 * Reports.
 *
 * Generation is a single synchronous request on the backend, so "progress" here is honest
 * about being indeterminate rather than animating a fake percentage. When it returns, the
 * download is triggered from a real anchor so the browser's own download UI takes over.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, FileDown, Loader2 } from "lucide-react";
import * as React from "react";
import { DisclosurePanel } from "@/components/reports/disclosure-panel";
import { ExportHistory, humanSize } from "@/components/reports/export-history";
import { FormatGrid } from "@/components/reports/format-grid";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  Field,
  InfoNote,
  LoadingBlock,
  SectionTitle,
  Select,
} from "@/components/ui/primitives";
import { PageHeader } from "@/components/workspace/shell";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { ExportFormat, ExportRecord } from "@/lib/types";

type ScopeKind = "project" | "journey" | "domain" | "scenario" | "selection";

const SCALES = [
  { value: 1, label: "1× — screen" },
  { value: 2, label: "2× — retina" },
  { value: 3, label: "3× — presentation" },
];

export function Reports({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const toast = useWorkspace((s) => s.toast);
  const activeScenarioId = useWorkspace((s) => s.activeScenarioId);
  const selectedNodeId = useWorkspace((s) => s.selectedNodeId);
  const highlight = useWorkspace((s) => s.highlight);

  const [formatId, setFormatId] = React.useState<string | null>(null);
  const [scope, setScope] = React.useState<ScopeKind>("project");
  const [journeyId, setJourneyId] = React.useState("");
  const [domainId, setDomainId] = React.useState("");
  const [scale, setScale] = React.useState(2);
  const [done, setDone] = React.useState<{ record: ExportRecord; url: string; interactive: boolean } | null>(
    null,
  );

  const formats = useQuery({
    queryKey: ["export-formats"],
    queryFn: () => api.exportFormats(),
    staleTime: Infinity,
  });

  const journeys = useQuery({
    queryKey: ["journeys", projectId, activeScenarioId],
    queryFn: () => api.journeys(projectId, activeScenarioId ?? undefined),
  });

  const overview = useQuery({
    queryKey: ["overview", projectId],
    queryFn: () => api.overview(projectId),
  });

  const history = useQuery({
    queryKey: ["exports", projectId],
    queryFn: () => api.listExports(projectId),
  });

  const selectionIds = React.useMemo(() => {
    if (highlight.nodes.length) return highlight.nodes;
    return selectedNodeId ? [selectedNodeId] : [];
  }, [highlight.nodes, selectedNodeId]);

  const format = (formats.data?.formats ?? []).find((item) => item.id === formatId) ?? null;

  const scopeValid =
    scope === "project" ||
    (scope === "journey" && Boolean(journeyId)) ||
    (scope === "domain" && Boolean(domainId)) ||
    (scope === "scenario" && Boolean(activeScenarioId)) ||
    (scope === "selection" && selectionIds.length > 0);

  const create = useMutation({
    mutationFn: () =>
      api.createExport(projectId, {
        format: formatId!,
        scenario_id: scope === "scenario" ? activeScenarioId : null,
        journey_id: scope === "journey" ? journeyId : null,
        domain_id: scope === "domain" ? domainId : null,
        node_ids: scope === "selection" ? selectionIds : [],
        scale: format?.id === "png" ? scale : undefined,
      }),
    onSuccess: (payload) => {
      setDone({
        record: payload.export,
        url: payload.download_url || api.downloadUrl(payload.export.id),
        interactive: payload.interactive,
      });
      queryClient.invalidateQueries({ queryKey: ["exports", projectId] });
      toast("success", `${payload.export.filename} is ready.`);
      triggerDownload(
        payload.download_url || api.downloadUrl(payload.export.id),
        payload.export.filename,
      );
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not generate that report."),
  });

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader
        icon={FileDown}
        title="Reports"
        subtitle="Produce something you can send to a person who does not have this app open. Every artefact carries its own provenance so it can be checked later."
        actions={
          activeScenarioId ? <Badge tone="degraded">A scenario is active</Badge> : undefined
        }
      />

      <div className="space-y-5 px-5 py-5">
        {/* ----------------------------------------------------------- formats */}
        <Card className="p-5">
          <SectionTitle>Choose a format</SectionTitle>
          {formats.isLoading ? (
            <LoadingBlock rows={4} label="Loading formats" />
          ) : formats.error ? (
            <ErrorState
              title="Could not load the export catalogue"
              detail={
                formats.error instanceof ApiError ? formats.error.message : String(formats.error)
              }
              correlationId={
                formats.error instanceof ApiError ? formats.error.correlationId : undefined
              }
              onRetry={() => formats.refetch()}
            />
          ) : (
            <>
              <FormatGrid
                formats={(formats.data?.formats ?? []) as ExportFormat[]}
                selected={formatId}
                onSelect={(id) => {
                  setFormatId(id);
                  setDone(null);
                }}
              />
              {formats.data?.note && (
                <p className="mt-3 border-t border-[var(--color-line)] pt-3 text-[12px] leading-snug text-[var(--color-muted)]">
                  {formats.data.note}
                </p>
              )}
            </>
          )}
        </Card>

        {/* ------------------------------------------------------------- scope */}
        <Card className="p-5">
          <SectionTitle>Choose what goes in it</SectionTitle>

          <div className="flex flex-wrap items-end gap-3">
            <div className="w-[260px]">
              <Field label="Scope">
                <Select
                  value={scope}
                  onChange={(event) => {
                    setScope(event.target.value as ScopeKind);
                    setDone(null);
                  }}
                >
                  <option value="project">The whole project</option>
                  <option value="journey">One journey</option>
                  <option value="domain">One domain</option>
                  <option value="scenario" disabled={!activeScenarioId}>
                    The active scenario{activeScenarioId ? "" : " — none is active"}
                  </option>
                  <option value="selection" disabled={selectionIds.length === 0}>
                    The current selection
                    {selectionIds.length ? ` (${selectionIds.length})` : " — nothing selected"}
                  </option>
                </Select>
              </Field>
            </div>

            {scope === "journey" && (
              <div className="w-[300px]">
                <Field label="Journey" error={journeyId ? undefined : "Choose a journey."}>
                  <Select value={journeyId} onChange={(event) => setJourneyId(event.target.value)}>
                    <option value="">Choose a journey…</option>
                    {(journeys.data?.journeys ?? []).map((journey) => (
                      <option key={journey.id} value={journey.id}>
                        {journey.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            )}

            {scope === "domain" && (
              <div className="w-[300px]">
                <Field label="Domain" error={domainId ? undefined : "Choose a domain."}>
                  <Select value={domainId} onChange={(event) => setDomainId(event.target.value)}>
                    <option value="">Choose a domain…</option>
                    {(overview.data?.domains ?? []).map((domain) => (
                      <option key={domain.id} value={domain.id}>
                        {domain.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            )}

            {format?.id === "png" && (
              <div className="w-[220px]">
                <Field label="Resolution" hint="Higher scale means a bigger file, not more detail.">
                  <Select
                    value={String(scale)}
                    onChange={(event) => setScale(Number(event.target.value))}
                  >
                    {SCALES.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            )}

            <Button
              variant="primary"
              onClick={() => {
                setDone(null);
                create.mutate();
              }}
              loading={create.isPending}
              disabled={!format || !format.available || !scopeValid}
            >
              <Download size={14} aria-hidden />
              Generate report
            </Button>
          </div>

          {scope === "scenario" && activeScenarioId && (
            <p className="mt-3 text-[12px] text-[var(--color-muted)]">
              The report will be produced from the scenario&apos;s graph. Findings, journeys and the
              disclosure still come from the base analysis, and the scenario is named on the cover.
            </p>
          )}
          {scope === "selection" && selectionIds.length > 0 && (
            <p className="mt-3 text-[12px] text-[var(--color-muted)]">
              <span className="numeral">{selectionIds.length}</span> node
              {selectionIds.length === 1 ? "" : "s"} currently selected or highlighted elsewhere in
              the workspace.
            </p>
          )}
          {!format && (
            <p className="mt-3 text-[12px] text-[var(--color-dim)]">
              Pick a format above first.
            </p>
          )}
        </Card>

        {/* ------------------------------------------------------------ result */}
        <div aria-live="polite">
          {create.isPending && (
            <Card className="p-4">
              <p className="flex items-center gap-2 text-[13px] text-[var(--color-ink)]">
                <Loader2 size={14} className="animate-spin text-[var(--color-accent-soft)]" aria-hidden />
                Rendering {format?.label ?? "the report"}…
              </p>
              <p className="mt-1.5 text-[12px] text-[var(--color-muted)]">
                This runs in one request, so there is no percentage to report. A PDF of a large
                estate can take several seconds.
              </p>
            </Card>
          )}

          {create.isError && (
            <ErrorState
              title="The report could not be generated"
              detail={
                create.error instanceof ApiError ? create.error.message : String(create.error)
              }
              hint={
                create.error instanceof ApiError
                  ? create.error.hint ||
                    "The backend logged the full traceback under the correlation ID below."
                  : undefined
              }
              correlationId={
                create.error instanceof ApiError ? create.error.correlationId : undefined
              }
              onRetry={() => create.mutate()}
            />
          )}

          {done && (
            <Card className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-start gap-2.5">
                  <CheckCircle2 size={16} className="mt-[2px] shrink-0 text-[var(--color-ok)]" aria-hidden />
                  <div className="min-w-0">
                    <p className="mono truncate text-[12.5px] text-[var(--color-ink)]">
                      {done.record.filename}
                    </p>
                    <p className="mt-0.5 text-[12px] text-[var(--color-muted)]">
                      {humanSize(done.record.size_bytes)} · scope {done.record.scope}
                      {done.interactive ? " · interactive" : " · static"}
                    </p>
                  </div>
                </div>
                <a
                  href={done.url}
                  download={done.record.filename}
                  className="inline-flex h-9 items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3.5 text-[13px] font-semibold text-[#0a0c10] transition-colors hover:bg-[var(--color-accent-soft)]"
                >
                  <Download size={14} aria-hidden />
                  Download again
                </a>
              </div>
              <p className="mt-2 text-[11.5px] text-[var(--color-dim)]">
                The download started automatically. If your browser blocked it, use the button.
              </p>
            </Card>
          )}
        </div>

        <ExportHistory
          exports={(history.data?.exports ?? []) as ExportRecord[]}
          loading={history.isLoading}
          error={history.error}
          onRetry={() => history.refetch()}
        />

        <DisclosurePanel />

        <InfoNote>
          Reports are written to this machine&apos;s data directory and never uploaded. Deleting
          them is done from Settings → Data.
        </InfoNote>
      </div>
    </div>
  );
}

/** Browsers only start a download from a real anchor activation, so make one and click it. */
function triggerDownload(url: string, filename: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
