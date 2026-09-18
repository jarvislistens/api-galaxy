"use client";

/**
 * Provider configuration.
 *
 * "Test connection" reports what the backend actually saw — status, latency and the models
 * it found — rather than a green tick. A tick that is not backed by a round trip is a lie
 * you only discover at the worst moment.
 */

import { useMutation } from "@tanstack/react-query";
import { Cpu, Eye, EyeOff, Globe, KeyRound, Plug, Save, Trash2 } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Button,
  Card,
  Field,
  InfoNote,
  Input,
  SectionTitle,
  cx,
} from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { ProviderHealth } from "@/lib/types";

const STATUS_TONE: Record<string, "ok" | "degraded" | "broken" | "neutral"> = {
  ready: "ok",
  not_configured: "neutral",
  unreachable: "broken",
  disabled: "neutral",
  error: "broken",
};

function StatusLine({ health }: { health: ProviderHealth | undefined }) {
  if (!health) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone={STATUS_TONE[health.status] ?? "neutral"}>
        {health.status.replace(/_/g, " ")}
      </Badge>
      <span className="text-[12px] text-[var(--color-muted)]">{health.detail}</span>
      {health.latency_ms != null && (
        <span className="numeral text-[11.5px] text-[var(--color-dim)]">
          {health.latency_ms < 1 ? "<1" : Math.round(health.latency_ms)} ms
        </span>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- Ollama */

export function OllamaCard({
  health,
  settings,
  onSave,
  saving,
}: {
  health: ProviderHealth | undefined;
  settings: Record<string, any>;
  onSave: (patch: Record<string, any>) => void;
  saving?: boolean;
}) {
  const [baseUrl, setBaseUrl] = React.useState(settings.ollama_base_url ?? "");
  const [model, setModel] = React.useState(settings.ollama_model ?? "");
  const [timeout, setTimeoutValue] = React.useState(String(settings.ollama_timeout ?? 180));
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setBaseUrl(settings.ollama_base_url ?? "");
    setModel(settings.ollama_model ?? "");
    setTimeoutValue(String(settings.ollama_timeout ?? 180));
  }, [settings.ollama_base_url, settings.ollama_model, settings.ollama_timeout]);

  const test = useMutation({
    mutationFn: () => api.testProvider("ollama"),
  });

  const submit = () => {
    const seconds = Number(timeout);
    if (!/^https?:\/\//.test(baseUrl.trim())) {
      setError("The base URL must start with http:// or https://.");
      return;
    }
    if (!Number.isFinite(seconds) || seconds < 5 || seconds > 900) {
      setError("Timeout must be between 5 and 900 seconds.");
      return;
    }
    setError(null);
    onSave({
      ollama_base_url: baseUrl.trim(),
      ollama_model: model.trim(),
      ollama_timeout: seconds,
    });
  };

  const result = test.data as ProviderHealth | undefined;

  return (
    <Card className="p-5">
      <SectionTitle action={<Badge tone="fact">Local · default</Badge>}>
        <span className="flex items-center gap-1.5">
          <Cpu size={13} className="text-[var(--color-accent-soft)]" aria-hidden />
          Ollama
        </span>
      </SectionTitle>

      <StatusLine health={health} />

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Field label="Base URL">
          <Input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
        </Field>
        <Field label="Model" hint={health?.available_models.length ? `Installed: ${health.available_models.join(", ")}` : undefined}>
          <Input value={model} onChange={(event) => setModel(event.target.value)} list="ollama-models" />
        </Field>
        <Field label="Timeout (seconds)" hint="5 to 900.">
          <Input
            type="number"
            min={5}
            max={900}
            className="numeral"
            value={timeout}
            onChange={(event) => setTimeoutValue(event.target.value)}
          />
        </Field>
      </div>

      <datalist id="ollama-models">
        {(health?.available_models ?? []).map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>

      {error && (
        <p role="alert" className="mt-2 text-[12px] text-[var(--color-broken)]">
          {error}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={submit} loading={saving}>
          <Save size={14} aria-hidden />
          Save
        </Button>
        <Button variant="secondary" onClick={() => test.mutate()} loading={test.isPending}>
          <Plug size={14} aria-hidden />
          Test connection
        </Button>
      </div>

      <div aria-live="polite">
        {test.isError && (
          <p role="alert" className="mt-3 text-[12.5px] text-[var(--color-broken)]">
            {test.error instanceof ApiError ? test.error.message : String(test.error)}
          </p>
        )}
        {result && (
          <div className="mt-3 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-base)] p-3">
            <StatusLine health={result} />
            <p className="mt-1.5 text-[12px] text-[var(--color-muted)]">
              {result.available_models.length
                ? `${result.available_models.length} model(s) installed: ${result.available_models.join(", ")}`
                : "No models were reported. Run `ollama pull qwen3:4b` to install one."}
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

/* ---------------------------------------------------------------------- Kimi */

export function KimiCard({
  health,
  settings,
  keyConfigured,
  externalEnabled,
  onSave,
  onKeyChanged,
  saving,
}: {
  health: ProviderHealth | undefined;
  settings: Record<string, any>;
  keyConfigured: boolean;
  externalEnabled: boolean;
  onSave: (patch: Record<string, any>) => void;
  onKeyChanged: () => void;
  saving?: boolean;
}) {
  const toast = useWorkspace((s) => s.toast);
  const [baseUrl, setBaseUrl] = React.useState(settings.kimi_base_url ?? "");
  const [model, setModel] = React.useState(settings.kimi_model ?? "");
  const [timeout, setTimeoutValue] = React.useState(String(settings.kimi_timeout ?? 120));
  const [apiKey, setApiKey] = React.useState("");
  const [reveal, setReveal] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [keyNote, setKeyNote] = React.useState<string | null>(null);

  React.useEffect(() => {
    setBaseUrl(settings.kimi_base_url ?? "");
    setModel(settings.kimi_model ?? "");
    setTimeoutValue(String(settings.kimi_timeout ?? 120));
  }, [settings.kimi_base_url, settings.kimi_model, settings.kimi_timeout]);

  const test = useMutation({ mutationFn: () => api.testProvider("kimi") });

  const setKey = useMutation({
    mutationFn: (value: string) => api.setKimiKey(value),
    onSuccess: (payload, value) => {
      setKeyNote(payload?.note ?? null);
      setApiKey("");
      onKeyChanged();
      toast(
        "success",
        value ? payload?.note || "API key stored." : "API key cleared.",
      );
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not store that key."),
  });

  const submit = () => {
    const seconds = Number(timeout);
    if (!/^https?:\/\//.test(baseUrl.trim())) {
      setError("The base URL must start with http:// or https://.");
      return;
    }
    if (!Number.isFinite(seconds) || seconds < 5 || seconds > 600) {
      setError("Timeout must be between 5 and 600 seconds.");
      return;
    }
    setError(null);
    onSave({
      kimi_base_url: baseUrl.trim(),
      kimi_model: model.trim(),
      kimi_timeout: seconds,
    });
  };

  const result = test.data as ProviderHealth | undefined;

  return (
    <Card className={cx("p-5", !externalEnabled && "opacity-70")}>
      <SectionTitle
        action={
          <Badge tone={keyConfigured ? "user" : "neutral"}>
            {keyConfigured ? "Key configured" : "No key"}
          </Badge>
        }
      >
        <span className="flex items-center gap-1.5">
          <Globe size={13} className="text-[var(--color-inferred)]" aria-hidden />
          Kimi — external, optional
        </span>
      </SectionTitle>

      <StatusLine health={health} />

      {!externalEnabled && (
        <p className="mt-3 text-[12.5px] text-[var(--color-degraded)]">
          External providers are switched off above. Nothing here will be used until you turn
          them back on, and turning them on does not by itself grant any project consent.
        </p>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Field label="Base URL">
          <Input
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            disabled={!externalEnabled}
          />
        </Field>
        <Field label="Model">
          <Input
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={!externalEnabled}
          />
        </Field>
        <Field label="Timeout (seconds)" hint="5 to 600.">
          <Input
            type="number"
            min={5}
            max={600}
            className="numeral"
            value={timeout}
            onChange={(event) => setTimeoutValue(event.target.value)}
            disabled={!externalEnabled}
          />
        </Field>
      </div>

      {error && (
        <p role="alert" className="mt-2 text-[12px] text-[var(--color-broken)]">
          {error}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={submit} loading={saving} disabled={!externalEnabled}>
          <Save size={14} aria-hidden />
          Save
        </Button>
        <Button
          variant="secondary"
          onClick={() => test.mutate()}
          loading={test.isPending}
          disabled={!externalEnabled}
        >
          <Plug size={14} aria-hidden />
          Test connection
        </Button>
      </div>

      {/* ------------------------------------------------------------- the key */}
      <div className="mt-5 border-t border-[var(--color-line)] pt-4">
        <p className="label-eyebrow mb-2">API key</p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-[340px]">
            <Field label="Kimi API key" hint="Sent to the backend once and never returned to this page.">
              <Input
                type={reveal ? "text" : "password"}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={keyConfigured ? "A key is already stored" : "sk-…"}
                autoComplete="off"
                disabled={!externalEnabled}
              />
            </Field>
          </div>
          <Button
            variant="ghost"
            onClick={() => setReveal((current) => !current)}
            aria-label={reveal ? "Hide the API key" : "Show the API key"}
            aria-pressed={reveal}
          >
            {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
          </Button>
          <Button
            variant="secondary"
            onClick={() => setKey.mutate(apiKey.trim())}
            loading={setKey.isPending && Boolean(apiKey)}
            disabled={!apiKey.trim() || !externalEnabled}
          >
            <KeyRound size={14} aria-hidden />
            Store key
          </Button>
          <Button
            variant="ghost"
            onClick={() => setKey.mutate("")}
            disabled={!keyConfigured}
            loading={setKey.isPending && !apiKey}
          >
            <Trash2 size={14} aria-hidden />
            Clear key
          </Button>
        </div>

        <div aria-live="polite">
          {keyNote && (
            <p className="mt-2 text-[12.5px] text-[var(--color-ink-2)]">{keyNote}</p>
          )}
        </div>

        <div className="mt-3">
          <InfoNote>
            The key goes into your operating system keychain when one is available. If it is
            not, it is held in memory for this session only and is gone when the backend
            restarts — the response above says which happened.
          </InfoNote>
        </div>
      </div>

      <div aria-live="polite">
        {test.isError && (
          <p role="alert" className="mt-3 text-[12.5px] text-[var(--color-broken)]">
            {test.error instanceof ApiError ? test.error.message : String(test.error)}
          </p>
        )}
        {result && (
          <div className="mt-3 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-base)] p-3">
            <StatusLine health={result} />
            {result.setup_hint && (
              <p className="mt-1.5 text-[12px] text-[var(--color-muted)]">{result.setup_hint}</p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
