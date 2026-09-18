"use client";

/**
 * The node inspector.
 *
 * This is where "how do you know that?" gets answered. Every panel is ordered so the
 * evidence comes before the interpretation: what the specification says, then what was
 * derived from it, then what somebody guessed — each labelled.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  FileCode2,
  Link2,
  Network,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
import * as React from "react";
import {
  Badge,
  Button,
  ErrorState,
  KeyValue,
  LoadingBlock,
  SectionTitle,
  Tooltip,
  cx,
} from "@/components/ui/primitives";
import { provenanceBucket } from "@/components/graph/graph-style";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";

const BUCKET_LABEL = {
  fact: "Specification fact",
  inferred: "Inferred",
  user: "Accepted by you",
} as const;

const BUCKET_TONE = { fact: "fact", inferred: "inferred", user: "user" } as const;

export function Inspector({ projectId }: { projectId: string }) {
  const selectedNodeId = useWorkspace((s) => s.selectedNodeId);
  const scenarioId = useWorkspace((s) => s.activeScenarioId);
  const select = useWorkspace((s) => s.select);
  const toast = useWorkspace((s) => s.toast);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["node", projectId, selectedNodeId, scenarioId],
    queryFn: () => api.node(projectId, selectedNodeId!, scenarioId ?? undefined),
    enabled: Boolean(selectedNodeId),
  });

  const decide = useMutation({
    mutationFn: ({ edgeId, action }: { edgeId: string; action: "accept" | "reject" }) =>
      api.decideEdge(projectId, edgeId, { action }),
    onSuccess: (_result, variables) => {
      toast(
        "success",
        variables.action === "accept"
          ? "Accepted. This relationship is now marked as your decision and is in the log."
          : "Rejected. It stays visible but no longer counts towards impact.",
      );
      queryClient.invalidateQueries({ queryKey: ["node", projectId] });
      queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
      queryClient.invalidateQueries({ queryKey: ["overview", projectId] });
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not record that."),
  });

  if (!selectedNodeId) {
    return (
      <div className="p-5">
        <p className="text-[12.5px] leading-relaxed text-[var(--color-dim)]">
          Select anything in the graph to see what it is, where it came from, and what
          depends on it.
        </p>
      </div>
    );
  }

  if (isLoading) return <div className="p-5"><LoadingBlock rows={5} label="Loading node" /></div>;
  if (error) {
    return (
      <div className="p-4">
        <ErrorState
          title="Could not load that node"
          detail={error instanceof ApiError ? error.message : String(error)}
          correlationId={error instanceof ApiError ? error.correlationId : undefined}
        />
      </div>
    );
  }
  if (!data) return null;

  const { node } = data;
  const bucket = provenanceBucket(node.provenance.source_kind, node.acceptance);
  const attrs = node.attrs ?? {};

  return (
    <div className="flex flex-col">
      <div className="border-b border-[var(--color-line)] px-4 py-3.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="label-eyebrow">{node.type}</p>
            <h3 className="mt-1 break-words text-[14px] font-semibold leading-snug text-[var(--color-ink)]">
              {node.label}
            </h3>
          </div>
          <Button variant="ghost" size="sm" onClick={() => select(null)} aria-label="Close inspector">
            <X size={13} />
          </Button>
        </div>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <Badge tone={BUCKET_TONE[bucket]}>{BUCKET_LABEL[bucket]}</Badge>
          {attrs.deprecated && <Badge tone="degraded">Deprecated</Badge>}
          {attrs.public && <Badge tone="broken">No authentication</Badge>}
          {attrs.sensitive_hint && <Badge tone="degraded">Marked sensitive</Badge>}
          {typeof node.provenance.confidence === "number" && bucket !== "fact" && (
            <Badge tone="neutral">
              {Math.round(node.provenance.confidence * 100)}% confidence
            </Badge>
          )}
        </div>
        {node.description && (
          <p className="mt-2.5 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
            {node.description}
          </p>
        )}
      </div>

      {/* ------------------------------------------------------- provenance */}
      <Section icon={FileCode2} title="How we know">
        <p className="text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
          {node.provenance.explanation}
        </p>
        <dl className="mt-2">
          <KeyValue label="Source">{sourceLabel(node.provenance.source_kind)}</KeyValue>
          {node.provenance.source_file && (
            <KeyValue label="File">
              <span className="mono break-all text-[11.5px]">{node.provenance.source_file}</span>
            </KeyValue>
          )}
          {node.provenance.source_pointer && (
            <KeyValue label="Location">
              <span className="mono break-all text-[11.5px]">{node.provenance.source_pointer}</span>
            </KeyValue>
          )}
          {node.provenance.provider && (
            <KeyValue label="Provider">
              {node.provenance.provider}
              {node.provenance.model ? ` · ${node.provenance.model}` : ""}
            </KeyValue>
          )}
        </dl>
        {data.evidence.length > 0 && (
          <ul className="mt-2 space-y-1">
            {data.evidence.map((item) => (
              <li
                key={item.id}
                className="mono rounded-[var(--radius-xs)] bg-[var(--color-surface-2)] px-2 py-1 text-[11px] text-[var(--color-muted)]"
              >
                {item.source_file}
                <span className="text-[var(--color-dim)]">#{item.pointer}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* ---------------------------------------------------------- details */}
      {Object.keys(attrs).length > 0 && (
        <Section icon={Network} title="Details">
          <dl>
            {attrs.method && <KeyValue label="Method">{String(attrs.method)}</KeyValue>}
            {attrs.path && (
              <KeyValue label="Path">
                <span className="mono break-all text-[11.5px]">{String(attrs.path)}</span>
              </KeyValue>
            )}
            {attrs.service && <KeyValue label="Service">{String(attrs.service)}</KeyValue>}
            {attrs.type_signature && (
              <KeyValue label="Type">
                <span className="mono">{String(attrs.type_signature)}</span>
              </KeyValue>
            )}
            {attrs.required !== undefined && (
              <KeyValue label="Required">{attrs.required ? "yes" : "no"}</KeyValue>
            )}
            {Array.isArray(attrs.security) && (
              <KeyValue label="Security">
                {attrs.security.length ? attrs.security.join(", ") : "none declared"}
              </KeyValue>
            )}
            {attrs.pagination && <KeyValue label="Pagination">{String(attrs.pagination)}</KeyValue>}
            {attrs.severity && <KeyValue label="Severity">{String(attrs.severity)}</KeyValue>}
            {attrs.recommendation && (
              <KeyValue label="Fix">{String(attrs.recommendation)}</KeyValue>
            )}
          </dl>
        </Section>
      )}

      {/* ---------------------------------------------------------- aliases */}
      {data.aliases.length > 0 && (
        <Section icon={Sparkles} title="May be the same as">
          <p className="mb-2 text-[11.5px] leading-snug text-[var(--color-dim)]">
            Suggestions, not facts. Accepting one changes every impact calculation that
            follows, and is written to the decision log.
          </p>
          <ul className="space-y-2">
            {data.aliases.map((alias) => (
              <li
                key={alias.id}
                className="rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] p-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    onClick={() => select(alias.id)}
                    className="min-w-0 text-left text-[12.5px] text-[var(--color-ink)] hover:text-[var(--color-accent-soft)]"
                  >
                    <span className="mono">{alias.name}</span>
                    {alias.service && (
                      <span className="ml-1.5 text-[11px] text-[var(--color-dim)]">
                        {alias.service}
                      </span>
                    )}
                  </button>
                  <Badge tone={alias.acceptance === "accepted" ? "user" : "inferred"}>
                    {alias.acceptance === "accepted"
                      ? "accepted"
                      : `${Math.round((alias.confidence ?? 0.7) * 100)}%`}
                  </Badge>
                </div>
                <p className="mt-1 text-[11.5px] leading-snug text-[var(--color-muted)]">
                  {alias.rationale}
                </p>
                {alias.acceptance === "proposed" && (
                  <div className="mt-2 flex gap-1.5">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => decide.mutate({ edgeId: alias.edge_id, action: "accept" })}
                      loading={decide.isPending}
                    >
                      <Check size={12} /> Accept
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => decide.mutate({ edgeId: alias.edge_id, action: "reject" })}
                    >
                      Reject
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ------------------------------------------------------------ risks */}
      {data.risks.length > 0 && (
        <Section icon={ShieldAlert} title="Findings on this node">
          <ul className="space-y-2">
            {data.risks.map((risk) => (
              <li key={risk.id} className="rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] p-2.5">
                <div className="flex items-start gap-2">
                  <AlertTriangle
                    size={13}
                    className={cx(
                      "mt-[2px] shrink-0",
                      risk.attrs?.severity === "high"
                        ? "text-[var(--color-broken)]"
                        : "text-[var(--color-degraded)]",
                    )}
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <p className="text-[12.5px] font-medium text-[var(--color-ink)]">{risk.label}</p>
                    <p className="mt-0.5 text-[11.5px] leading-snug text-[var(--color-muted)]">
                      {risk.description}
                    </p>
                    <Badge tone={risk.attrs?.heuristic ? "inferred" : "fact"} className="mt-1.5">
                      {risk.attrs?.heuristic ? "Heuristic finding" : "Deterministic finding"}
                    </Badge>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ------------------------------------------------------- dependents */}
      {data.dependents.length > 0 && (
        <Section icon={Link2} title={`${data.dependents.length} things depend on this`}>
          <ul className="space-y-0.5">
            {data.dependents.slice(0, 18).map((dependent) => (
              <li key={dependent.id}>
                <button
                  onClick={() => select(dependent.id)}
                  className="flex w-full items-center gap-2 rounded-[var(--radius-xs)] px-1.5 py-1 text-left text-[12px] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-ink)]"
                >
                  <span className="w-5 shrink-0 text-[10.5px] text-[var(--color-dim)]">
                    {dependent.distance}↑
                  </span>
                  <span className="min-w-0 flex-1 truncate">{dependent.label}</span>
                  <span className="shrink-0 text-[10.5px] text-[var(--color-dim)]">
                    {dependent.type}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {data.dependents.length > 18 && (
            <p className="mt-1.5 text-[11.5px] text-[var(--color-dim)]">
              and {data.dependents.length - 18} more
            </p>
          )}
        </Section>
      )}

      {/* --------------------------------------------------------- relations */}
      {(data.outgoing.length > 0 || data.incoming.length > 0) && (
        <Section icon={Network} title="Connections">
          <RelationList title="Points at" items={data.outgoing} onSelect={select} />
          <RelationList title="Pointed at by" items={data.incoming} onSelect={select} />
        </Section>
      )}
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-[var(--color-line)] px-4 py-3.5">
      <SectionTitle>
        <span className="flex items-center gap-1.5">
          <Icon size={13} className="text-[var(--color-dim)]" />
          {title}
        </span>
      </SectionTitle>
      {children}
    </section>
  );
}

function RelationList({
  title,
  items,
  onSelect,
}: {
  title: string;
  items: any[];
  onSelect: (id: string) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="mb-2 last:mb-0">
      <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--color-dim)]">
        {title}
      </p>
      <ul className="space-y-0.5">
        {items.slice(0, 12).map((edge) => (
          <li key={edge.id}>
            <Tooltip label={edge.provenance?.explanation ?? edge.label}>
              <button
                onClick={() => onSelect(edge.other_id)}
                className="flex w-full items-center gap-2 rounded-[var(--radius-xs)] px-1.5 py-1 text-left text-[12px] hover:bg-[var(--color-surface-2)]"
              >
                <span
                  className={cx(
                    "h-0 w-4 shrink-0 border-t",
                    edge.stroke === "dashed"
                      ? "border-dashed border-[var(--color-inferred)]"
                      : edge.stroke === "dotted"
                        ? "border-dotted border-[var(--color-user)]"
                        : "border-solid border-[var(--color-fact)]",
                  )}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate text-[var(--color-ink-2)]">
                  {edge.other}
                </span>
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-[var(--color-dim)]">
                  {String(edge.type).replace(/_/g, " ").toLowerCase()}
                </span>
              </button>
            </Tooltip>
          </li>
        ))}
      </ul>
    </div>
  );
}

function sourceLabel(kind: string): string {
  return (
    {
      specification: "Read from the specification",
      deterministic_rule: "Computed by a rule",
      bundled_analysis: "Bundled Demo Analysis",
      ai_inference: "Proposed by a model",
      user_edit: "Your decision",
      scenario: "Scenario change",
    }[kind] ?? kind
  );
}
