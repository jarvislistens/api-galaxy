"use client";

/**
 * Agreement, disagreement, and the human who decides.
 *
 * Each row shows both providers' reasoning side by side rather than a merged sentence,
 * because the whole value of running two models is seeing where they diverge. Every button
 * here writes to the append-only decision log — nothing is silently merged into the graph.
 */

import { Check, GitMerge, Handshake, Split, Swords, X } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  SectionTitle,
  Tab,
  TabPanel,
  Tabs,
  TabsBar,
  cx,
} from "@/components/ui/primitives";
import type { ArenaRelation } from "@/lib/types";

export type DecisionAction =
  | "accept_ollama"
  | "accept_kimi"
  | "accept_deterministic"
  | "merge"
  | "reject_both"
  | "edit";

const PROVIDER_LABEL: Record<string, string> = {
  deterministic: "Deterministic",
  ollama: "Ollama",
  kimi: "Kimi",
};

const SECTIONS = [
  {
    id: "consensus",
    label: "Consensus",
    icon: Handshake,
    blurb: "Both providers produced the same relationship. Agreement is not proof, but it is a reason to look first.",
  },
  {
    id: "only_a",
    label: "Only A",
    icon: Split,
    blurb: "Found by the first provider and not the second.",
  },
  {
    id: "only_b",
    label: "Only B",
    icon: Split,
    blurb: "Found by the second provider and not the first.",
  },
  {
    id: "conflicts",
    label: "Conflicts",
    icon: Swords,
    blurb: "Both providers linked the same pair but disagreed about the relationship. These need a person.",
  },
] as const;

export function ComparisonSections({
  consensus,
  onlyA,
  onlyB,
  conflicts,
  providerA,
  providerB,
  decided,
  onDecide,
  busy,
}: {
  consensus: ArenaRelation[];
  onlyA: ArenaRelation[];
  onlyB: ArenaRelation[];
  conflicts: ArenaRelation[];
  providerA: string;
  providerB: string;
  /** Keyed by relation key, so a row that has been resolved says so. */
  decided: Record<string, DecisionAction>;
  onDecide: (relation: ArenaRelation, action: DecisionAction) => void;
  busy?: boolean;
}) {
  const [tab, setTab] = React.useState<string>("consensus");
  const data: Record<string, ArenaRelation[]> = {
    consensus,
    only_a: onlyA,
    only_b: onlyB,
    conflicts,
  };

  return (
    <Card className="p-5">
      <SectionTitle>Where they agree and where they do not</SectionTitle>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsBar aria-label="Comparison sections" className="w-fit">
          {SECTIONS.map((section) => (
            <Tab key={section.id} value={section.id}>
              {section.label}{" "}
              <span className="numeral ml-1 text-[var(--color-dim)]">
                {data[section.id].length}
              </span>
            </Tab>
          ))}
        </TabsBar>

        {SECTIONS.map((section) => (
          <TabPanel key={section.id} value={section.id} className="mt-4 focus-visible:outline-none">
            <p className="mb-3 text-[12.5px] text-[var(--color-muted)]">
              {section.id === "only_a"
                ? `Found by ${PROVIDER_LABEL[providerA] ?? providerA} and not by ${PROVIDER_LABEL[providerB] ?? providerB}.`
                : section.id === "only_b"
                  ? `Found by ${PROVIDER_LABEL[providerB] ?? providerB} and not by ${PROVIDER_LABEL[providerA] ?? providerA}.`
                  : section.blurb}
            </p>

            {data[section.id].length === 0 ? (
              <EmptyState
                icon={<section.icon size={18} aria-hidden />}
                title={`Nothing in ${section.label.toLowerCase()}`}
                body="This run produced no rows here. That is a result, not a failure."
              />
            ) : (
              <ul className="space-y-3">
                {data[section.id].map((relation) => (
                  <RelationRow
                    key={relationKey(relation)}
                    relation={relation}
                    providerA={providerA}
                    providerB={providerB}
                    decision={decided[relationKey(relation)]}
                    onDecide={onDecide}
                    busy={busy}
                  />
                ))}
              </ul>
            )}
          </TabPanel>
        ))}
      </Tabs>
    </Card>
  );
}

export function relationKey(relation: ArenaRelation): string {
  return `${relation.source_id}|${relation.relation}|${relation.target_id}`;
}

function acceptAction(provider: string): DecisionAction | null {
  if (provider === "ollama") return "accept_ollama";
  if (provider === "kimi") return "accept_kimi";
  if (provider === "deterministic") return "accept_deterministic";
  return null;
}

function RelationRow({
  relation,
  providerA,
  providerB,
  decision,
  onDecide,
  busy,
}: {
  relation: ArenaRelation;
  providerA: string;
  providerB: string;
  decision?: DecisionAction;
  onDecide: (relation: ArenaRelation, action: DecisionAction) => void;
  busy?: boolean;
}) {
  const sides = [providerA, providerB];

  return (
    <li className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-[var(--color-ink)]">
            <span className="font-medium">{relation.source_label ?? relation.source_id}</span>
            <span className="mx-2 text-[var(--color-dim)]">→</span>
            <span className="font-medium">{relation.target_label ?? relation.target_id}</span>
          </p>
          <p className="mono mt-1 text-[11px] text-[var(--color-dim)]">
            {relation.source_id} → {relation.target_id}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge tone="accent">{relation.relation}</Badge>
          <Badge tone="neutral">{relation.verdict.replace(/_/g, " ")}</Badge>
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {sides.map((provider) => {
          const present = relation.providers.includes(provider);
          const confidence = relation.confidences?.[provider];
          const rationale = relation.rationales?.[provider];
          return (
            <div
              key={provider}
              className={cx(
                "rounded-[var(--radius-sm)] border p-3",
                present
                  ? "border-[var(--color-line-strong)] bg-[var(--color-surface-2)]"
                  : "border-dashed border-[var(--color-line)] bg-transparent",
              )}
            >
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-[12px] font-medium text-[var(--color-ink-2)]">
                  {PROVIDER_LABEL[provider] ?? provider}
                </p>
                <p className="numeral text-[11.5px] text-[var(--color-dim)]">
                  {present && confidence != null
                    ? `${Math.round(confidence * 100)}% confidence`
                    : present
                      ? "no confidence reported"
                      : "did not produce this"}
                </p>
              </div>
              <p className="mt-1.5 text-[12px] leading-snug text-[var(--color-muted)]">
                {present ? rationale || "No rationale was given." : "—"}
              </p>
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--color-line)] pt-3">
        {decision ? (
          <Badge tone="user">
            Recorded: {decision.replace(/_/g, " ")}
          </Badge>
        ) : (
          <>
            {sides.map((provider, index) => {
              const action = acceptAction(provider);
              if (!action) return null;
              return (
                <Button
                  key={provider}
                  size="sm"
                  variant="secondary"
                  disabled={busy || !relation.providers.includes(provider)}
                  onClick={() => onDecide(relation, action)}
                >
                  <Check size={12} aria-hidden />
                  Accept {index === 0 ? "A" : "B"} · {PROVIDER_LABEL[provider] ?? provider}
                </Button>
              );
            })}
            <Button
              size="sm"
              variant="secondary"
              disabled={busy || relation.providers.length < 2}
              onClick={() => onDecide(relation, "merge")}
            >
              <GitMerge size={12} aria-hidden />
              Merge
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDecide(relation, "reject_both")}>
              <X size={12} aria-hidden />
              Reject both
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
