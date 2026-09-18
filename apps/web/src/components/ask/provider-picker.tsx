"use client";

/**
 * Which engine answers the question.
 *
 * The default is the one that cannot hallucinate. Providers that are not ready stay
 * visible but unselectable, with the reason attached — hiding them would make the app
 * look like it has fewer options than it does, and leave the reader guessing.
 */

import { Cpu, Globe, ShieldCheck } from "lucide-react";
import * as React from "react";
import { Badge, Tooltip, cx } from "@/components/ui/primitives";
import type { ProviderHealth } from "@/lib/types";

export type ProviderKind = "deterministic" | "ollama" | "kimi";

const OPTIONS: {
  kind: ProviderKind;
  label: string;
  detail: string;
  icon: typeof Cpu;
  external: boolean;
}[] = [
  {
    kind: "deterministic",
    label: "No model — graph only",
    detail: "Computed from the graph. Nothing is generated, so nothing can be invented.",
    icon: ShieldCheck,
    external: false,
  },
  {
    kind: "ollama",
    label: "Local & Private",
    detail: "A model running on this machine. Nothing leaves your laptop.",
    icon: Cpu,
    external: false,
  },
  {
    kind: "kimi",
    label: "External",
    detail: "A third-party service over the internet. You will be shown what is sent first.",
    icon: Globe,
    external: true,
  },
];

export function ProviderPicker({
  value,
  onChange,
  providers,
  loading,
}: {
  value: ProviderKind;
  onChange: (kind: ProviderKind) => void;
  providers: ProviderHealth[];
  loading?: boolean;
}) {
  const health = React.useMemo(() => {
    const map = new Map<string, ProviderHealth>();
    for (const provider of providers) map.set(provider.kind, provider);
    return map;
  }, [providers]);

  const selected = OPTIONS.find((option) => option.kind === value);
  const selectedHealth = health.get(value);

  return (
    <div>
      <p className="label-eyebrow mb-1.5">Answering engine</p>
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Answering engine">
        {OPTIONS.map((option) => {
          const state = health.get(option.kind);
          const ready = loading ? option.kind === "deterministic" : Boolean(state?.ready);
          const active = value === option.kind;
          const Icon = option.icon;

          const button = (
            <button
              key={option.kind}
              role="radio"
              aria-checked={active}
              aria-disabled={!ready}
              onClick={() => {
                if (ready) onChange(option.kind);
              }}
              className={cx(
                "flex items-center gap-2 rounded-[var(--radius-sm)] border px-2.5 py-1.5 text-[12.5px]",
                "transition-[background,border-color,color] duration-150",
                active
                  ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_14%,transparent)] text-[var(--color-ink)]"
                  : "border-[var(--color-line-strong)] bg-[var(--color-surface-2)] text-[var(--color-muted)] hover:text-[var(--color-ink)]",
                !ready && "cursor-not-allowed opacity-45",
              )}
            >
              <Icon size={13} aria-hidden />
              <span>{option.label}</span>
              {option.external && (
                <Badge tone="degraded" className="ml-0.5">
                  leaves this machine
                </Badge>
              )}
              {!ready && (
                <span className="text-[11px] text-[var(--color-dim)]">· not ready</span>
              )}
            </button>
          );

          return ready ? (
            <Tooltip key={option.kind} label={option.detail}>
              {button}
            </Tooltip>
          ) : (
            <Tooltip
              key={option.kind}
              label={
                <span>
                  <span className="block font-medium text-[var(--color-ink)]">
                    {state?.detail ?? "This provider is not available."}
                  </span>
                  {state?.setup_hint && (
                    <span className="mt-1 block">{state.setup_hint}</span>
                  )}
                </span>
              }
            >
              {button}
            </Tooltip>
          );
        })}
      </div>

      <p className="mt-1.5 text-[11.5px] leading-snug text-[var(--color-dim)]">
        {selected?.detail}
        {selectedHealth?.model ? ` · ${selectedHealth.model}` : ""}
      </p>
    </div>
  );
}
