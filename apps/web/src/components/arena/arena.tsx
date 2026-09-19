"use client";

/**
 * Model Arena.
 *
 * Same bounded context, same schema, two providers, one table. The page is deliberately
 * unglamorous about models: latency, tokens, estimated cost and invented references sit in
 * the same row, and a provider that is not set up is shown disabled with the reason rather
 * than hidden.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Globe, Play, Swords } from "lucide-react";
import * as React from "react";
import {
  ComparisonSections,
  relationKey,
  type DecisionAction,
} from "@/components/arena/comparison-sections";
import { DecisionLog, type DecisionRecord } from "@/components/arena/decision-log";
import { MetricsTable } from "@/components/arena/metrics-table";
import { PricingEditor } from "@/components/settings/pricing-editor";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  InfoNote,
  LoadingBlock,
  SectionTitle,
  Select,
  cx,
} from "@/components/ui/primitives";
import { PageHeader } from "@/components/workspace/shell";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { ArenaPayload, ArenaRelation, ProviderHealth } from "@/lib/types";

type ModeId = "local" | "external" | "arena";

const MODES: {
  id: ModeId;
  label: string;
  detail: string;
  icon: typeof Cpu;
  providers: [string, string];
  requires: string[];
}[] = [
  {
    id: "local",
    label: "Local & Private (Ollama)",
    detail:
      "The local model against the deterministic baseline. Nothing leaves this machine, and the baseline needs no model at all.",
    icon: Cpu,
    providers: ["deterministic", "ollama"],
    requires: ["ollama"],
  },
  {
    id: "external",
    label: "Kimi API (optional external)",
    detail:
      "The external model against the deterministic baseline. Requires an API key and this project's consent before anything is sent.",
    icon: Globe,
    providers: ["deterministic", "kimi"],
    requires: ["kimi"],
  },
  {
    id: "arena",
    label: "Compare Both",
    detail:
      "Ollama and Kimi on the identical context and schema. This is the comparison the page is named after.",
    icon: Swords,
    providers: ["ollama", "kimi"],
    requires: ["ollama", "kimi"],
  },
];

const PROVIDER_LABEL: Record<string, string> = {
  deterministic: "Deterministic (no model)",
  ollama: "Ollama (local)",
  kimi: "Kimi (external)",
};

export function Arena({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const toast = useWorkspace((s) => s.toast);

  const [mode, setMode] = React.useState<ModeId>("local");
  const [providerA, setProviderA] = React.useState("deterministic");
  const [providerB, setProviderB] = React.useState("ollama");
  const [domainId, setDomainId] = React.useState("");
  const [result, setResult] = React.useState<ArenaPayload | null>(null);
  const [decided, setDecided] = React.useState<Record<string, DecisionAction>>({});

  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.providers(),
  });

  const overview = useQuery({
    queryKey: ["overview", projectId],
    queryFn: () => api.overview(projectId),
  });

  const decisions = useQuery({
    queryKey: ["decisions", projectId],
    queryFn: () => api.decisions(projectId),
  });

  const health = React.useMemo(() => {
    const map: Record<string, ProviderHealth> = {};
    for (const item of providers.data?.providers ?? []) map[item.kind] = item;
    return map;
  }, [providers.data]);

  // Until health has actually come back, nothing is "not ready" — it is unknown. Showing a
  // provider as unavailable before we have asked is a lie the reader has no way to check.
  const known = providers.isSuccess;
  const ready = (kind: string) => !known || Boolean(health[kind]?.ready);

  const pickMode = (next: ModeId) => {
    setMode(next);
    const config = MODES.find((item) => item.id === next)!;
    setProviderA(config.providers[0]);
    setProviderB(config.providers[1]);
  };

  const run = useMutation({
    mutationFn: () => api.arena(projectId, [providerA, providerB], domainId || undefined),
    onSuccess: (payload) => {
      setResult(payload);
      setDecided({});
      toast("success", "Arena run complete.");
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "The arena run failed."),
  });

  const decide = useMutation({
    mutationFn: ({ relation, action }: { relation: ArenaRelation; action: DecisionAction }) => {
      const provider =
        action === "accept_ollama"
          ? "ollama"
          : action === "accept_kimi"
            ? "kimi"
            : action === "accept_deterministic"
              ? "deterministic"
              : "";
      const model =
        result?.metrics.find((metric) => metric.provider === provider)?.model ?? "";
      return api.arenaDecision(projectId, {
        action,
        subject: `${relation.source_label ?? relation.source_id} —${relation.relation}→ ${
          relation.target_label ?? relation.target_id
        }`,
        payload: {
          source_id: relation.source_id,
          target_id: relation.target_id,
          relation: relation.relation,
          verdict: relation.verdict,
          confidences: relation.confidences,
        },
        provider,
        model,
        source_references: [relation.source_id, relation.target_id],
      });
    },
    onSuccess: (_payload, variables) => {
      setDecided((current) => ({
        ...current,
        [relationKey(variables.relation)]: variables.action,
      }));
      queryClient.invalidateQueries({ queryKey: ["decisions", projectId] });
      toast("success", "Decision recorded in the append-only log.");
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not record that decision."),
  });

  const sameProvider = providerA === providerB;
  const blocked = !ready(providerA) || !ready(providerB) || sameProvider;

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader
        icon={Swords}
        title="Model Arena"
        subtitle="Send the identical bounded context to two providers under the same schema, then compare what they found, what they invented, how long it took and what it would have cost."
        actions={
          providers.data?.prompt_template_version ? (
            <Badge tone="neutral">
              Prompt template {providers.data.prompt_template_version}
            </Badge>
          ) : undefined
        }
      />

      <div className="space-y-5 px-5 py-5">
        {/* ------------------------------------------------------------ modes */}
        <div>
          <p className="label-eyebrow mb-2.5">Choose a matchup</p>
          <div className="grid gap-3 lg:grid-cols-3">
            {MODES.map((config) => {
              const missing = config.requires.filter((kind) => !ready(kind));
              const disabled = missing.length > 0;
              const active = mode === config.id;
              const Icon = config.icon;
              return (
                <button
                  key={config.id}
                  type="button"
                  onClick={() => !disabled && pickMode(config.id)}
                  disabled={disabled}
                  aria-pressed={active}
                  className={cx(
                    "rounded-[var(--radius-lg)] border p-4 text-left transition-colors duration-200",
                    disabled && "cursor-not-allowed opacity-60",
                    active
                      ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_10%,transparent)]"
                      : "border-[var(--color-line)] bg-[var(--color-surface)] hover:border-[var(--color-line-strong)]",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2">
                      <Icon size={15} className="text-[var(--color-accent-soft)]" aria-hidden />
                      <span className="text-[13.5px] font-semibold text-[var(--color-ink)]">
                        {config.label}
                      </span>
                    </span>
                    {!known ? (
                      <Badge tone="neutral">Checking…</Badge>
                    ) : disabled ? (
                      <Badge tone="neutral">Not ready</Badge>
                    ) : active ? (
                      <Badge tone="accent">Selected</Badge>
                    ) : null}
                  </div>
                  <p className="mt-2 text-[12.5px] leading-snug text-[var(--color-muted)]">
                    {config.detail}
                  </p>
                  {missing.map((kind) => (
                    <p key={kind} className="mt-2 text-[12px] leading-snug text-[var(--color-degraded)]">
                      {health[kind]?.setup_hint ||
                        health[kind]?.detail ||
                        `${PROVIDER_LABEL[kind] ?? kind} is not available.`}
                    </p>
                  ))}
                </button>
              );
            })}
          </div>
          {providers.isLoading && (
            <div className="mt-3">
              <LoadingBlock rows={2} label="Checking provider health" />
            </div>
          )}
        </div>

        {/* ------------------------------------------------------------- run */}
        <Card className="p-5">
          <SectionTitle>Run</SectionTitle>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-[240px]">
              <Field label="Provider A">
                <Select value={providerA} onChange={(event) => setProviderA(event.target.value)}>
                  {Object.keys(PROVIDER_LABEL).map((kind) => (
                    <option key={kind} value={kind} disabled={!ready(kind)}>
                      {PROVIDER_LABEL[kind]}
                      {ready(kind) ? "" : " — not ready"}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <div className="w-[240px]">
              <Field label="Provider B">
                <Select value={providerB} onChange={(event) => setProviderB(event.target.value)}>
                  {Object.keys(PROVIDER_LABEL).map((kind) => (
                    <option key={kind} value={kind} disabled={!ready(kind)}>
                      {PROVIDER_LABEL[kind]}
                      {ready(kind) ? "" : " — not ready"}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <div className="w-[280px]">
              {/* The hint lives below the row, not inside this Field. With `items-end`
                  a hint here makes only this column taller, so its label and select get
                  pushed up and stop lining up with Provider A and B. */}
              <Field label="Scope">
                <Select value={domainId} onChange={(event) => setDomainId(event.target.value)}>
                  <option value="">The whole estate</option>
                  {(overview.data?.domains ?? []).map((domain) => (
                    <option key={domain.id} value={domain.id}>
                      {domain.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <Button
              variant="primary"
              onClick={() => run.mutate()}
              loading={run.isPending}
              disabled={blocked || !known}
            >
              <Play size={14} aria-hidden />
              Run arena
            </Button>
          </div>

          <p className="mt-2 text-[12px] text-[var(--color-dim)]">
            Narrowing the scope to one domain keeps the context small, which is fairer to a
            local model.
          </p>

          {sameProvider && (
            <p role="alert" className="mt-3 text-[12px] text-[var(--color-broken)]">
              Pick two different providers — the arena compares two runs, not one against itself.
            </p>
          )}
          {!sameProvider && blocked && (
            <p className="mt-3 text-[12px] text-[var(--color-degraded)]">
              {[providerA, providerB]
                .filter((kind) => !ready(kind))
                .map((kind) => health[kind]?.setup_hint || health[kind]?.detail || `${kind} is not ready.`)
                .join(" ")}
            </p>
          )}
          <div className="mt-3">
            <InfoNote>
              A local model on a laptop can take a minute or more on a whole estate. The request
              is not cancellable once it starts.
            </InfoNote>
          </div>
        </Card>

        {/* --------------------------------------------------------- results */}
        <div aria-live="polite" className="space-y-5">
          {run.isPending && (
            <Card className="p-5">
              <LoadingBlock rows={5} label="Running both providers" />
              <p className="mt-3 text-[12.5px] text-[var(--color-muted)]">
                Both providers are running against the same context. This finishes when the
                slower one finishes.
              </p>
            </Card>
          )}

          {run.isError && (
            <ErrorState
              title="The arena run failed"
              detail={run.error instanceof ApiError ? run.error.message : String(run.error)}
              hint={run.error instanceof ApiError ? run.error.hint : undefined}
              correlationId={run.error instanceof ApiError ? run.error.correlationId : undefined}
              onRetry={() => run.mutate()}
            />
          )}

          {!run.isPending && !result && !run.isError && (
            <Card className="p-5">
              <EmptyState
                icon={<Swords size={22} aria-hidden />}
                title="No run yet"
                body="Pick a matchup and press Run arena. Nothing is sent anywhere until you do, and an external provider additionally needs this project's consent."
              />
            </Card>
          )}

          {result && (
            <>
              <MetricsTable metrics={result.metrics} disclaimer={result.pricing_disclaimer} />

              {result.notes?.length > 0 && (
                <Card className="p-4">
                  <p className="label-eyebrow mb-1.5">Notes from this run</p>
                  <ul className="space-y-1">
                    {result.notes.map((note) => (
                      <li key={note} className="text-[12.5px] text-[var(--color-ink-2)]">
                        {note}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              <AgreementCard
                alias={result.alias_agreement}
                domain={result.domain_agreement}
                providerA={providerA}
                providerB={providerB}
              />

              <ComparisonSections
                consensus={result.consensus}
                onlyA={result.only_a}
                onlyB={result.only_b}
                conflicts={result.conflicts}
                providerA={providerA}
                providerB={providerB}
                decided={decided}
                onDecide={(relation, action) => decide.mutate({ relation, action })}
                busy={decide.isPending}
              />
            </>
          )}
        </div>

        <DecisionLog
          decisions={(decisions.data?.decisions ?? []) as DecisionRecord[]}
          note={decisions.data?.note}
          loading={decisions.isLoading}
          error={decisions.error}
          onRetry={() => decisions.refetch()}
        />

        <PricingEditor />
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- agreement */

function AgreementCard({
  alias,
  domain,
  providerA,
  providerB,
}: {
  alias: Record<string, any>;
  domain: Record<string, any>;
  providerA: string;
  providerB: string;
}) {
  const rows = [
    { label: "Aliases", data: alias },
    { label: "Domains", data: domain },
  ].filter((row) => row.data && Object.keys(row.data).length > 0);

  if (!rows.length) return null;

  return (
    <Card className="p-5">
      <SectionTitle>Overlap on the rest of the output</SectionTitle>
      <div className="scroll-x">
        <table className="w-full border-collapse text-[12.5px]">
          <caption className="sr-only">
            How far the two providers agreed on aliases and domains.
          </caption>
          <thead>
            <tr className="border-b border-[var(--color-line)]">
              {["", "Agreed", `Only ${providerA}`, `Only ${providerB}`, "Jaccard"].map((label, index) => (
                <th
                  key={index}
                  scope="col"
                  className="px-2.5 py-2 text-left text-[11px] uppercase tracking-wide text-[var(--color-dim)]"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-b border-[var(--color-line)]">
                <th scope="row" className="px-2.5 py-2 text-left font-normal text-[var(--color-ink)]">
                  {row.label}
                </th>
                <td className="numeral px-2.5 py-2 text-[var(--color-ink-2)]">
                  {row.data.agreed ?? 0}
                </td>
                <td className="numeral px-2.5 py-2 text-[var(--color-ink-2)]">
                  {row.data[`only_${providerA}`] ?? 0}
                </td>
                <td className="numeral px-2.5 py-2 text-[var(--color-ink-2)]">
                  {row.data[`only_${providerB}`] ?? 0}
                </td>
                <td className="numeral px-2.5 py-2 text-[var(--color-ink-2)]">
                  {row.data.jaccard ?? 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11.5px] text-[var(--color-dim)]">
        Jaccard is the size of the overlap divided by the size of the union: 1 is identical
        output, 0 is no shared item at all.
      </p>
    </Card>
  );
}
