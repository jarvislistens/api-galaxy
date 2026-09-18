"use client";

/**
 * Repair mode.
 *
 * The hard rule of this file: "Journey restored" is only ever rendered from the backend's
 * own re-validation. `all_valid === true`, or the journey's name appearing in
 * `journeys_restored`, are the only two things that may produce that phrase. Applying a
 * repair is never treated as evidence that it worked.
 */

import { useMutation } from "@tanstack/react-query";
import {
  CheckCircle2,
  ClipboardCheck,
  Copy,
  Pencil,
  Play,
  ShieldQuestion,
  Sparkles,
  ThumbsDown,
  Wrench,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import {
  Badge,
  Button,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  InfoNote,
  Input,
  LoadingBlock,
  SectionTitle,
  Select,
  cx,
} from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { JourneyValidation, ProviderHealth, Repair } from "@/lib/types";

interface DecisionOutcome {
  repairId: string;
  journeys_before: JourneyValidation[];
  journeys_after: JourneyValidation[];
  journeys_restored: string[];
  all_valid: boolean;
  patch: string[];
  migration_steps: string[];
}

export function RepairsPanel({
  projectId,
  scenarioId,
  providers,
  hasChanges,
  onChanged,
}: {
  projectId: string;
  scenarioId: string | null;
  providers: ProviderHealth[];
  hasChanges: boolean;
  onChanged: () => void;
}) {
  const toast = useWorkspace((s) => s.toast);
  const [provider, setProvider] = React.useState("deterministic");
  const [repairs, setRepairs] = React.useState<Repair[]>([]);
  const [warnings, setWarnings] = React.useState<string[]>([]);
  const [deterministicCount, setDeterministicCount] = React.useState(0);
  const [outcome, setOutcome] = React.useState<DecisionOutcome | null>(null);
  const [editing, setEditing] = React.useState<Repair | null>(null);
  const [proposed, setProposed] = React.useState(false);

  const propose = useMutation({
    mutationFn: () => api.proposeRepairs(projectId, scenarioId!, provider),
    onSuccess: (payload) => {
      setRepairs((payload.repairs ?? []) as Repair[]);
      setWarnings(payload.warnings ?? []);
      setDeterministicCount(payload.deterministic_count ?? 0);
      setOutcome(null);
      setProposed(true);
    },
  });

  const decide = useMutation({
    mutationFn: ({
      repair,
      action,
      params,
      title,
    }: {
      repair: Repair;
      action: "apply" | "reject";
      params?: Record<string, any>;
      title?: string;
    }) => api.decideRepair(projectId, scenarioId!, repair.id, { action, params, title }),
    onSuccess: (payload, variables) => {
      setRepairs((current) =>
        current.map((item) =>
          item.id === variables.repair.id
            ? ((payload.repair ?? {
                ...item,
                status: variables.action === "apply" ? "applied" : "rejected",
              }) as Repair)
            : item,
        ),
      );
      if (variables.action === "apply") {
        setOutcome({
          repairId: variables.repair.id,
          journeys_before: payload.journeys_before ?? [],
          journeys_after: payload.journeys_after ?? [],
          journeys_restored: payload.journeys_restored ?? [],
          all_valid: Boolean(payload.all_valid),
          patch: payload.patch ?? [],
          migration_steps: payload.migration_steps ?? [],
        });
      } else {
        setOutcome(null);
        toast("info", "Rejected. It stays in the log but is not applied.");
      }
      onChanged();
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not record that decision."),
  });

  const providerOptions = React.useMemo(
    () =>
      providers.filter((item) => item.kind === "deterministic" || item.kind === "ollama"),
    [providers],
  );

  if (!scenarioId) {
    return (
      <Card className="p-5">
        <EmptyState
          icon={<Wrench size={20} aria-hidden />}
          title="Pick a scenario first"
          body="Repairs are proposed against the changes in a scenario, so there has to be one."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <SectionTitle>Propose repairs</SectionTitle>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-[300px]">
            <Field
              label="Provider"
              hint="Deterministic repairs are derived mechanically from the change. A model may propose others, always labelled as proposed."
            >
              <Select value={provider} onChange={(event) => setProvider(event.target.value)}>
                {providerOptions.map((item) => (
                  <option key={item.kind} value={item.kind} disabled={!item.ready}>
                    {item.kind === "deterministic" ? "Deterministic (no model)" : "Ollama (local)"}
                    {item.model ? ` — ${item.model}` : ""}
                    {item.ready ? "" : " — not ready"}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Button
            variant="primary"
            onClick={() => propose.mutate()}
            loading={propose.isPending}
            disabled={!hasChanges}
          >
            <Sparkles size={14} aria-hidden />
            Propose repairs
          </Button>
          {!hasChanges && (
            <p className="text-[12px] text-[var(--color-muted)]">
              Add a change first — there is nothing to repair yet.
            </p>
          )}
        </div>

        {providerOptions.some((item) => item.kind === provider && !item.ready) && (
          <p className="mt-3 text-[12px] text-[var(--color-degraded)]">
            {providerOptions.find((item) => item.kind === provider)?.setup_hint ||
              "That provider is not ready."}
          </p>
        )}
      </Card>

      {propose.isPending && (
        <Card className="p-5">
          <LoadingBlock rows={4} label="Proposing repairs" />
        </Card>
      )}

      {propose.isError && (
        <ErrorState
          title="Could not propose repairs"
          detail={
            propose.error instanceof ApiError ? propose.error.message : String(propose.error)
          }
          hint={propose.error instanceof ApiError ? propose.error.hint : undefined}
          correlationId={
            propose.error instanceof ApiError ? propose.error.correlationId : undefined
          }
          onRetry={() => propose.mutate()}
        />
      )}

      {warnings.length > 0 && (
        <Card className="p-4">
          <p className="label-eyebrow mb-1.5">Warnings from the provider</p>
          <ul className="space-y-1">
            {warnings.map((warning) => (
              <li key={warning} className="text-[12.5px] text-[var(--color-degraded)]">
                {warning}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {proposed && !propose.isPending && repairs.length === 0 && (
        <Card className="p-5">
          <EmptyState
            icon={<ShieldQuestion size={20} aria-hidden />}
            title="No repair was proposed"
            body="That provider had nothing mechanical to suggest for these changes. Try the other provider, or undo the change."
          />
        </Card>
      )}

      {repairs.length > 0 && (
        <p className="text-[12px] text-[var(--color-muted)]">
          <span className="numeral">{repairs.length}</span> proposal
          {repairs.length === 1 ? "" : "s"} · <span className="numeral">{deterministicCount}</span>{" "}
          derived deterministically
        </p>
      )}

      <div className="space-y-4">
        {repairs.map((repair) => (
          <RepairCard
            key={repair.id}
            projectId={projectId}
            repair={repair}
            outcome={outcome?.repairId === repair.id ? outcome : null}
            busy={decide.isPending}
            onApply={() => decide.mutate({ repair, action: "apply" })}
            onReject={() => decide.mutate({ repair, action: "reject" })}
            onEdit={() => setEditing(repair)}
          />
        ))}
      </div>

      {editing && (
        <EditRepairDialog
          repair={editing}
          onClose={() => setEditing(null)}
          onSubmit={(params, title) => {
            decide.mutate({ repair: editing, action: "apply", params, title });
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

/* --------------------------------------------------------------------- card */

function RepairCard({
  projectId,
  repair,
  outcome,
  busy,
  onApply,
  onReject,
  onEdit,
}: {
  projectId: string;
  repair: Repair;
  outcome: DecisionOutcome | null;
  busy: boolean;
  onApply: () => void;
  onReject: () => void;
  onEdit: () => void;
}) {
  const [checked, setChecked] = React.useState<Set<number>>(new Set());
  const applied = repair.status === "applied";
  const rejected = repair.status === "rejected";

  return (
    <Card
      className={cx(
        "p-5",
        applied && "border-[color-mix(in_oklab,var(--color-ok)_34%,transparent)]",
        rejected && "opacity-60",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-[14px] font-semibold text-[var(--color-ink)]">{repair.title}</h3>
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-muted)]">
            {repair.rationale}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          <Badge tone={repair.deterministic ? "fact" : "inferred"}>
            {repair.deterministic ? "Deterministic" : "Proposed by a model"}
          </Badge>
          {repair.confidence != null && (
            <Badge tone="neutral">
              <span className="numeral">{Math.round(repair.confidence * 100)}%</span> confidence
            </Badge>
          )}
          {applied && <Badge tone="ok">Applied</Badge>}
          {rejected && <Badge tone="neutral">Rejected</Badge>}
        </div>
      </div>

      {repair.patch.length > 0 && (
        <div className="mt-4">
          <p className="label-eyebrow mb-1.5">Patch</p>
          <pre className="scroll-x mono rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-base)] p-3 text-[11.5px] leading-relaxed">
            {repair.patch.map((line, index) => (
              <div
                key={index}
                className={cx(
                  line.startsWith("+") && "text-[var(--color-ok)]",
                  line.startsWith("-") && !line.startsWith("---") && "text-[var(--color-broken)]",
                  (line.startsWith("---") || (!line.startsWith("+") && !line.startsWith("-"))) &&
                    "text-[var(--color-dim)]",
                )}
              >
                {line}
              </div>
            ))}
          </pre>
        </div>
      )}

      {repair.migration_steps.length > 0 && (
        <div className="mt-4">
          <p className="label-eyebrow mb-1.5">Migration checklist</p>
          <ul className="space-y-1.5">
            {repair.migration_steps.map((step, index) => (
              <li key={step}>
                <label className="flex cursor-pointer items-start gap-2 text-[12.5px] leading-snug text-[var(--color-ink-2)]">
                  <input
                    type="checkbox"
                    checked={checked.has(index)}
                    onChange={() =>
                      setChecked((current) => {
                        const next = new Set(current);
                        if (next.has(index)) next.delete(index);
                        else next.add(index);
                        return next;
                      })
                    }
                    className="mt-[3px] h-3.5 w-3.5 shrink-0 accent-[var(--color-accent)]"
                  />
                  <span className={checked.has(index) ? "text-[var(--color-dim)] line-through" : ""}>
                    {step}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11.5px] text-[var(--color-dim)]">
            Ticking a box is a note to yourself. It is not sent anywhere and does not change the
            graph.
          </p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={onApply} disabled={busy || applied}>
          <CheckCircle2 size={14} aria-hidden />
          {applied ? "Applied" : "Apply"}
        </Button>
        <Button variant="secondary" onClick={onEdit} disabled={busy}>
          <Pencil size={14} aria-hidden />
          Edit
        </Button>
        <Button variant="ghost" onClick={onReject} disabled={busy || rejected}>
          <ThumbsDown size={14} aria-hidden />
          Reject
        </Button>
      </div>

      {/* ------------------------------------------------- validation outcome */}
      {outcome && (
        <div
          className="mt-4 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-base)] p-4"
          aria-live="polite"
        >
          <p className="label-eyebrow mb-2">After re-validating every journey</p>

          {outcome.all_valid ? (
            <p className="flex items-center gap-2 text-[13px] font-medium text-[var(--color-ok)]">
              <CheckCircle2 size={14} aria-hidden />
              Every journey validates again. All {outcome.journeys_after.length} pass.
            </p>
          ) : outcome.journeys_restored.length > 0 ? (
            <div>
              <p className="flex items-center gap-2 text-[13px] font-medium text-[var(--color-ok)]">
                <CheckCircle2 size={14} aria-hidden />
                {outcome.journeys_restored.length} journey
                {outcome.journeys_restored.length === 1 ? "" : "s"} restored
              </p>
              <ul className="mt-1.5 space-y-0.5">
                {outcome.journeys_restored.map((name) => (
                  <li key={name} className="text-[12.5px] text-[var(--color-ink-2)]">
                    {name} — journey restored
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="flex items-start gap-2 text-[13px] text-[var(--color-degraded)]">
              <XCircle size={14} className="mt-[2px] shrink-0" aria-hidden />
              No journey was restored by this repair. Validation still fails, so nothing here
              claims otherwise.
            </p>
          )}

          <ul className="mt-3 space-y-1">
            {outcome.journeys_after.map((journey) => {
              const wasBroken = outcome.journeys_before.find(
                (item) => item.journey_id === journey.journey_id,
              );
              const restored =
                journey.ok && Boolean(wasBroken) && !wasBroken!.ok;
              return (
                <li
                  key={journey.journey_id}
                  className="flex items-baseline justify-between gap-3 text-[12.5px]"
                >
                  <span className="min-w-0 truncate text-[var(--color-ink-2)]">
                    {journey.journey_name}
                  </span>
                  <span className="shrink-0">
                    {restored ? (
                      <Badge tone="ok">Journey restored</Badge>
                    ) : journey.ok ? (
                      <Badge tone="neutral">Still OK</Badge>
                    ) : (
                      <Badge tone="broken">Still broken</Badge>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>

          <div className="mt-4">
            <Link
              href={`/workspace/${projectId}/journeys?journey=journey:place-order`}
              className="inline-flex h-9 items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-3.5 text-[13px] font-medium text-[var(--color-ink)] transition-colors hover:bg-[var(--color-surface-3)]"
            >
              <Play size={14} aria-hidden />
              Replay checkout
            </Link>
            <p className="mt-1.5 text-[11.5px] text-[var(--color-dim)]">
              Opens the Place Order journey with this scenario still active, so you watch the
              changed graph rather than the base one.
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------- dialog */

function EditRepairDialog({
  repair,
  onClose,
  onSubmit,
}: {
  repair: Repair;
  onClose: () => void;
  onSubmit: (params: Record<string, any>, title: string) => void;
}) {
  const [title, setTitle] = React.useState(repair.title);
  const [values, setValues] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(repair.params ?? {}).map(([key, value]) => [key, String(value ?? "")]),
    ),
  );
  const keys = Object.keys(repair.params ?? {});

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Edit this repair"
      description="Your edit is applied and recorded in the decision log as your decision, not the provider's."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => onSubmit(values, title.trim() || repair.title)}>
            Apply edited repair
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Title">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} />
        </Field>

        {keys.length === 0 ? (
          <InfoNote>
            This repair has no parameters to edit. Applying it from here still records the edit as
            yours.
          </InfoNote>
        ) : (
          keys.map((key) => (
            <Field key={key} label={key.replace(/_/g, " ")}>
              <Input
                value={values[key] ?? ""}
                onChange={(event) =>
                  setValues((current) => ({ ...current, [key]: event.target.value }))
                }
              />
            </Field>
          ))
        )}
      </div>
    </Dialog>
  );
}

/* ------------------------------------------------------------ change summary */

export function ChangeSummaryPanel({
  markdown,
  patch,
  migrationSteps,
  loading,
}: {
  markdown: string;
  patch: string[];
  migrationSteps: string[];
  loading?: boolean;
}) {
  const toast = useWorkspace((s) => s.toast);
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      toast("success", "Change summary copied as Markdown.");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast("error", "The browser refused clipboard access. Select the text and copy it.");
    }
  };

  return (
    <Card className="p-5">
      <SectionTitle
        action={
          <Button variant="secondary" size="sm" onClick={copy} disabled={!markdown}>
            {copied ? <ClipboardCheck size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
            Copy markdown
          </Button>
        }
      >
        Change summary
      </SectionTitle>

      {loading ? (
        <LoadingBlock rows={4} label="Loading the change summary" />
      ) : markdown ? (
        <>
          <pre className="scroll-x mono max-h-80 overflow-y-auto whitespace-pre-wrap rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-base)] p-3 text-[11.5px] leading-relaxed text-[var(--color-ink-2)]">
            {markdown}
          </pre>
          <p className="mt-2 text-[11.5px] text-[var(--color-dim)]">
            <span className="numeral">{patch.length}</span> patch line
            {patch.length === 1 ? "" : "s"} ·{" "}
            <span className="numeral">{migrationSteps.length}</span> migration step
            {migrationSteps.length === 1 ? "" : "s"}. Paste it into a pull request or a ticket.
          </p>
        </>
      ) : (
        <p className="text-[12.5px] text-[var(--color-dim)]">
          Nothing to summarise yet — add a change to the scenario.
        </p>
      )}
    </Card>
  );
}
