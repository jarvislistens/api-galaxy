"use client";

/**
 * The one dialog in the product that is allowed to interrupt.
 *
 * Nothing goes to a third party until this has been read and accepted. It shows the
 * destination, the size, the redaction result and the payload itself — and the primary
 * action says what it does ("Send to Kimi"), not "OK".
 */

import { useQuery } from "@tanstack/react-query";
import { Globe, ShieldCheck } from "lucide-react";
import * as React from "react";
import { ContextPreviewBody } from "@/components/ask/context-preview";
import {
  Button,
  Dialog,
  ErrorState,
  KeyValue,
  LoadingBlock,
  SectionTitle,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";

export function ConsentDialog({
  projectId,
  question,
  open,
  onOpenChange,
  onApprove,
  sending,
}: {
  projectId: string;
  question: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: () => void;
  sending?: boolean;
}) {
  const preview = useQuery({
    queryKey: ["external-preview", projectId],
    queryFn: () => api.externalPreview(projectId),
    enabled: open,
  });

  const context = useQuery({
    queryKey: ["context-preview", projectId, question.trim()],
    queryFn: () => api.contextPreview(projectId, question.trim()),
    enabled: open && question.trim().length > 0,
  });

  const data = preview.data;
  const sanitization = data?.sanitization;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      wide
      title="This request leaves your machine"
      description="Review exactly what would be sent before anything is transmitted."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel — keep it local
          </Button>
          <Button
            variant="primary"
            loading={sending}
            disabled={preview.isLoading || Boolean(preview.error)}
            onClick={onApprove}
          >
            <Globe size={13} aria-hidden /> Send to {data?.provider ?? "the external provider"}
          </Button>
        </>
      }
    >
      {preview.isLoading ? (
        <LoadingBlock label="Building the external request preview" rows={5} />
      ) : preview.error ? (
        <ErrorState
          title="The preview could not be built"
          detail={(preview.error as ApiError).message}
          hint={(preview.error as ApiError).hint}
          correlationId={(preview.error as ApiError).correlationId}
          onRetry={() => void preview.refetch()}
        />
      ) : (
        <div className="space-y-4">
          <div
            role="alert"
            className="rounded-[var(--radius-md)] border border-[color-mix(in_oklab,var(--color-degraded)_42%,transparent)] bg-[color-mix(in_oklab,var(--color-degraded)_10%,transparent)] px-3.5 py-3 text-[12.5px] leading-relaxed text-[var(--color-ink-2)]"
          >
            {data?.warning ??
              "This will send the content below to a third-party service over the internet."}
          </div>

          <dl className="rounded-[var(--radius-md)] border border-[var(--color-line)] px-3.5 py-2">
            <KeyValue label="Provider">{data?.provider}</KeyValue>
            <KeyValue label="Model">
              <span className="mono">{data?.model}</span>
            </KeyValue>
            <KeyValue label="Endpoint">
              <span className="mono break-all">{data?.endpoint}</span>
            </KeyValue>
            <KeyValue label="Payload size">
              <span className="numeral">
                {Number(data?.estimated_bytes ?? 0).toLocaleString()} bytes
              </span>
            </KeyValue>
            <KeyValue label="Fingerprint">
              <span className="mono break-all">{data?.fingerprint}</span>
            </KeyValue>
          </dl>

          <div className="flex items-start gap-2.5 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3.5 py-3">
            <ShieldCheck
              size={15}
              className="mt-[2px] shrink-0 text-[var(--color-ok)]"
              aria-hidden
            />
            <div className="min-w-0">
              <p className="label-eyebrow">Redaction</p>
              <p className="mt-1 text-[12.5px] text-[var(--color-ink-2)]">
                {sanitization?.summary ?? "No redaction report was returned."}
              </p>
              {sanitization && (
                <p className="numeral mt-1 text-[11.5px] text-[var(--color-dim)]">
                  {sanitization.total_redactions ?? 0} redaction
                  {sanitization.total_redactions === 1 ? "" : "s"} ·{" "}
                  {Number(sanitization.original_bytes ?? 0).toLocaleString()} bytes in,{" "}
                  {Number(sanitization.sanitized_bytes ?? 0).toLocaleString()} out
                  {sanitization.truncated ? " · truncated" : ""}
                </p>
              )}
            </div>
          </div>

          {context.data && (
            <div>
              <SectionTitle>What this question pulls in</SectionTitle>
              <ContextPreviewBody data={context.data} />
            </div>
          )}

          {data?.payload_preview?.prompt && (
            <div>
              <SectionTitle>The prompt, verbatim</SectionTitle>
              <pre className="mono max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] p-3 text-[11px] leading-relaxed text-[var(--color-muted)]">
                {String(data.payload_preview.prompt)}
              </pre>
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}
