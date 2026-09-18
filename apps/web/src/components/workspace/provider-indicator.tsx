"use client";

/**
 * The privacy indicator.
 *
 * Always visible, always honest: it says which provider is active, whether anything can
 * leave the machine, and what to do about it. "Local" is the default state and it is
 * stated positively rather than as an absence.
 */

import { useQuery } from "@tanstack/react-query";
import { Cloud, HardDrive, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Tooltip, cx } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export function ProviderIndicator() {
  const params = useParams<{ projectId?: string }>();
  const { data } = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.providers(),
    staleTime: 30_000,
  });

  const external = data?.providers.find((p) => p.external);
  const ollama = data?.providers.find((p) => p.kind === "ollama");
  const externalEnabled = Boolean(data?.settings?.external_providers_enabled);
  const externalUsable = externalEnabled && external?.ready;

  const state = externalUsable
    ? {
        icon: Cloud,
        tone: "text-[var(--color-degraded)]",
        label: "External available",
        detail:
          "An external provider is configured. Nothing is sent until you approve a request " +
          "preview for a project.",
      }
    : ollama?.ready
      ? {
          icon: ShieldCheck,
          tone: "text-[var(--color-ok)]",
          label: "Local",
          detail: `Ollama is ready (${ollama.model}). Nothing leaves this machine.`,
        }
      : {
          icon: HardDrive,
          tone: "text-[var(--color-muted)]",
          label: "Local",
          detail:
            "No model is running, so answers come from the deterministic graph provider. " +
            "Everything still works, and nothing leaves this machine.",
        };

  const Icon = data ? state.icon : ShieldAlert;
  const href = params?.projectId ? `/workspace/${params.projectId}/settings` : "/";

  return (
    <Tooltip label={data ? state.detail : "Checking providers…"}>
      <Link
        href={href}
        className="flex h-8 items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2 text-[11.5px] transition-colors hover:border-[var(--color-dim)]"
        aria-label={data ? `${state.label} — ${state.detail}` : "Checking providers"}
      >
        <Icon size={13} className={cx("shrink-0", data ? state.tone : "text-[var(--color-dim)]")}
              aria-hidden />
        <span className="hidden text-[var(--color-ink-2)] md:inline">
          {data ? state.label : "…"}
        </span>
      </Link>
    </Tooltip>
  );
}
