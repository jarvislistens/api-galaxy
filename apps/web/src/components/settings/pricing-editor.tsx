"use client";

/**
 * The pricing table.
 *
 * Shipped prices are examples, and they are labelled as examples every single time they are
 * shown — a cost estimate that looks like a quote is worse than no estimate at all. The
 * disclaimer comes from the API and is rendered verbatim, never paraphrased.
 *
 * Mounted on both Settings and Model Arena, so it owns its own fetching.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  Input,
  LoadingBlock,
  SectionTitle,
} from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";

interface PricingRow {
  input_per_million: number;
  output_per_million: number;
  note: string;
  updated_by: string;
  updated_at: string;
}

const PROVIDER_LABEL: Record<string, string> = {
  deterministic: "Deterministic (no model)",
  ollama: "Ollama (local)",
  kimi: "Kimi (external)",
};

function formatTimestamp(value: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString();
}

export function PricingEditor({ compact }: { compact?: boolean }) {
  const queryClient = useQueryClient();
  const toast = useWorkspace((s) => s.toast);

  const pricing = useQuery({
    queryKey: ["pricing"],
    queryFn: () => api.pricing(),
  });

  const [drafts, setDrafts] = React.useState<Record<string, { input: string; output: string; note: string }>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  const rows: [string, PricingRow][] = React.useMemo(
    () => Object.entries((pricing.data?.pricing ?? {}) as Record<string, PricingRow>),
    [pricing.data],
  );

  const save = useMutation({
    mutationFn: (body: {
      provider: string;
      input_per_million: number;
      output_per_million: number;
      note: string;
    }) => api.updatePricing(body),
    onSuccess: (_payload, variables) => {
      queryClient.invalidateQueries({ queryKey: ["pricing"] });
      setDrafts((current) => {
        const next = { ...current };
        delete next[variables.provider];
        return next;
      });
      toast("success", `Pricing for ${PROVIDER_LABEL[variables.provider] ?? variables.provider} saved.`);
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not save that price."),
  });

  const draftFor = (provider: string, row: PricingRow) =>
    drafts[provider] ?? {
      input: String(row.input_per_million),
      output: String(row.output_per_million),
      note: row.note ?? "",
    };

  const edit = (provider: string, row: PricingRow, patch: Partial<{ input: string; output: string; note: string }>) =>
    setDrafts((current) => ({
      ...current,
      [provider]: { ...draftFor(provider, row), ...patch },
    }));

  const submit = (provider: string, row: PricingRow) => {
    const draft = draftFor(provider, row);
    const input = Number(draft.input);
    const output = Number(draft.output);
    if (!Number.isFinite(input) || input < 0 || input > 10000) {
      setErrors((current) => ({ ...current, [provider]: "Input price must be a number between 0 and 10000." }));
      return;
    }
    if (!Number.isFinite(output) || output < 0 || output > 10000) {
      setErrors((current) => ({ ...current, [provider]: "Output price must be a number between 0 and 10000." }));
      return;
    }
    setErrors((current) => {
      const next = { ...current };
      delete next[provider];
      return next;
    });
    save.mutate({
      provider,
      input_per_million: input,
      output_per_million: output,
      note: draft.note,
    });
  };

  return (
    <Card className={compact ? "p-4" : "p-5"}>
      <SectionTitle action={<Badge tone="degraded">Shipped values are EXAMPLES</Badge>}>
        Pricing — USD per 1M tokens
      </SectionTitle>

      {pricing.isLoading ? (
        <LoadingBlock rows={4} label="Loading pricing" />
      ) : pricing.error ? (
        <ErrorState
          title="Could not load pricing"
          detail={pricing.error instanceof ApiError ? pricing.error.message : String(pricing.error)}
          correlationId={
            pricing.error instanceof ApiError ? pricing.error.correlationId : undefined
          }
          onRetry={() => pricing.refetch()}
        />
      ) : (
        <>
          <div className="scroll-x">
            <table className="w-full min-w-[720px] border-collapse text-[12.5px]">
              <caption className="sr-only">
                Editable token prices per provider, with who last changed each one and when.
              </caption>
              <thead>
                <tr className="border-b border-[var(--color-line)]">
                  <th scope="col" className="px-2 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                    Provider
                  </th>
                  <th scope="col" className="px-2 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                    Input / 1M
                  </th>
                  <th scope="col" className="px-2 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                    Output / 1M
                  </th>
                  <th scope="col" className="px-2 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                    Note
                  </th>
                  <th scope="col" className="px-2 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                    Last updated
                  </th>
                  <th scope="col" className="px-2 py-2">
                    <span className="sr-only">Save</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([provider, row]) => {
                  const draft = draftFor(provider, row);
                  const dirty = Boolean(drafts[provider]);
                  return (
                    <React.Fragment key={provider}>
                      <tr className="border-b border-[var(--color-line)]">
                        <th scope="row" className="px-2 py-2.5 text-left font-normal text-[var(--color-ink)]">
                          {PROVIDER_LABEL[provider] ?? provider}
                        </th>
                        <td className="px-2 py-2.5">
                          <Input
                            aria-label={`Input price per million tokens for ${PROVIDER_LABEL[provider] ?? provider}`}
                            type="number"
                            step="0.01"
                            min="0"
                            className="h-8 w-[104px] numeral"
                            value={draft.input}
                            onChange={(event) => edit(provider, row, { input: event.target.value })}
                          />
                        </td>
                        <td className="px-2 py-2.5">
                          <Input
                            aria-label={`Output price per million tokens for ${PROVIDER_LABEL[provider] ?? provider}`}
                            type="number"
                            step="0.01"
                            min="0"
                            className="h-8 w-[104px] numeral"
                            value={draft.output}
                            onChange={(event) => edit(provider, row, { output: event.target.value })}
                          />
                        </td>
                        <td className="px-2 py-2.5">
                          <Input
                            aria-label={`Note for ${PROVIDER_LABEL[provider] ?? provider}`}
                            className="h-8 min-w-[220px]"
                            value={draft.note}
                            onChange={(event) => edit(provider, row, { note: event.target.value })}
                          />
                        </td>
                        <td className="px-2 py-2.5 text-[11.5px] text-[var(--color-dim)]">
                          {formatTimestamp(row.updated_at)}
                          <span className="block">by {row.updated_by || "app"}</span>
                        </td>
                        <td className="px-2 py-2.5 text-right">
                          <Button
                            size="sm"
                            variant={dirty ? "primary" : "secondary"}
                            onClick={() => submit(provider, row)}
                            loading={save.isPending && save.variables?.provider === provider}
                            disabled={!dirty}
                          >
                            <Save size={12} aria-hidden />
                            Save
                          </Button>
                        </td>
                      </tr>
                      {errors[provider] && (
                        <tr>
                          <td colSpan={6} className="px-2 pb-2">
                            <p role="alert" className="text-[12px] text-[var(--color-broken)]">
                              {errors[provider]}
                            </p>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {pricing.data?.disclaimer && (
            <p className="mt-3 border-t border-[var(--color-line)] pt-3 text-[12px] leading-snug text-[var(--color-muted)]">
              {pricing.data.disclaimer}
            </p>
          )}
        </>
      )}
    </Card>
  );
}
