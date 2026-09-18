"use client";

/**
 * Settings.
 *
 * Privacy is first on the page because it is the switch with the largest consequence.
 * Turning external providers off also clears every recorded per-project consent, so turning
 * it back on cannot quietly resume sending anything — that is stated next to the switch,
 * not discovered afterwards.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings as SettingsIcon, ShieldCheck } from "lucide-react";
import * as React from "react";
import { AboutPanel } from "@/components/settings/about-panel";
import { DataControls } from "@/components/settings/data-controls";
import { PricingEditor } from "@/components/settings/pricing-editor";
import { KimiCard, OllamaCard } from "@/components/settings/provider-cards";
import {
  Badge,
  Card,
  ErrorState,
  LoadingBlock,
  SectionTitle,
  Switch,
} from "@/components/ui/primitives";
import { PageHeader } from "@/components/workspace/shell";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { ProviderHealth } from "@/lib/types";

export function Settings({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const toast = useWorkspace((s) => s.toast);

  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.providers(),
  });

  const meta = useQuery({
    queryKey: ["meta"],
    queryFn: () => api.meta(),
    staleTime: Infinity,
  });

  const saveConfig = useMutation({
    mutationFn: (patch: Record<string, any>) => api.updateProviderConfig(patch),
    onSuccess: (_payload, patch) => {
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      if ("external_providers_enabled" in patch) {
        toast(
          patch.external_providers_enabled ? "info" : "success",
          patch.external_providers_enabled
            ? "External providers are on. Each project still needs its own consent before anything is sent."
            : "External providers are off and every recorded consent has been cleared.",
        );
      } else {
        toast("success", "Provider settings saved.");
      }
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not save those settings."),
  });

  const health = React.useMemo(() => {
    const map: Record<string, ProviderHealth> = {};
    for (const item of providers.data?.providers ?? []) map[item.kind] = item;
    return map;
  }, [providers.data]);

  const settings = providers.data?.settings ?? {};
  const externalEnabled = Boolean(settings.external_providers_enabled);

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader
        icon={SettingsIcon}
        title="Settings"
        subtitle="Providers, privacy, pricing and the data this machine is holding. Nothing here is synced anywhere."
        actions={
          providers.data?.prompt_template_version ? (
            <Badge tone="neutral">Prompt template {providers.data.prompt_template_version}</Badge>
          ) : undefined
        }
      />

      <div className="max-w-6xl space-y-5 px-5 py-5">
        {providers.isLoading ? (
          <Card className="p-5">
            <LoadingBlock rows={5} label="Loading provider settings" />
          </Card>
        ) : providers.error ? (
          <ErrorState
            title="Could not load provider settings"
            detail={
              providers.error instanceof ApiError
                ? providers.error.message
                : String(providers.error)
            }
            correlationId={
              providers.error instanceof ApiError ? providers.error.correlationId : undefined
            }
            onRetry={() => providers.refetch()}
          />
        ) : (
          <>
            {/* -------------------------------------------------------- privacy */}
            <Card raised className="p-5">
              <SectionTitle action={<Badge tone={externalEnabled ? "inferred" : "fact"}>
                {externalEnabled ? "External calls allowed" : "Fully local"}
              </Badge>}>
                <span className="flex items-center gap-1.5">
                  <ShieldCheck size={13} className="text-[var(--color-ok)]" aria-hidden />
                  Privacy
                </span>
              </SectionTitle>

              <Switch
                id="external-providers"
                checked={externalEnabled}
                onCheckedChange={(value) =>
                  saveConfig.mutate({ external_providers_enabled: value })
                }
                label="Allow external providers"
                description={
                  "Off by default in spirit: with this switched off, no request can leave this machine " +
                  "for any reason, and every per-project consent you have previously granted is cleared " +
                  "at the same moment. Switching it back on does not restore those consents — each " +
                  "project has to be consented to again."
                }
              />

              <ul className="mt-4 space-y-1.5 border-t border-[var(--color-line)] pt-4">
                {[
                  "Ollama runs on this machine and is the default for every AI feature.",
                  "The app is fully usable with no model at all — the deterministic provider needs nothing.",
                  "Before any external request you get a preview of the exact payload, with credentials, emails, phone numbers and internal URLs already stripped.",
                ].map((line) => (
                  <li key={line} className="text-[12.5px] leading-snug text-[var(--color-muted)]">
                    {line}
                  </li>
                ))}
              </ul>
            </Card>

            {/* ------------------------------------------------------ providers */}
            <OllamaCard
              health={health.ollama}
              settings={settings}
              onSave={(patch) => saveConfig.mutate(patch)}
              saving={saveConfig.isPending}
            />

            <KimiCard
              health={health.kimi}
              settings={settings}
              keyConfigured={Boolean(providers.data?.kimi_key_configured)}
              externalEnabled={externalEnabled}
              onSave={(patch) => saveConfig.mutate(patch)}
              onKeyChanged={() =>
                queryClient.invalidateQueries({ queryKey: ["providers"] })
              }
              saving={saveConfig.isPending}
            />
          </>
        )}

        {/* --------------------------------------------------------- pricing */}
        <PricingEditor />

        {/* ------------------------------------------------------------ data */}
        <DataControls />

        {/* ----------------------------------------------------------- about */}
        <AboutPanel
          meta={meta.data}
          loading={meta.isLoading}
          error={meta.error}
          onRetry={() => meta.refetch()}
        />

        <p className="pb-4 text-[11.5px] text-[var(--color-dim)]">
          Settings are global to this installation, not to project{" "}
          <span className="mono">{projectId}</span>.
        </p>
      </div>
    </div>
  );
}
