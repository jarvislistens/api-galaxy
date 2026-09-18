"use client";

/**
 * Following an import job.
 *
 * The backend streams progress over server-sent events, but the stream only carries
 * *future* publishes — a job that finished before the browser opened the connection would
 * leave the stream silent forever. So this hook runs the stream and a slow poll together
 * and takes whichever reaches a terminal state first.
 */

import { Loader2, XCircle } from "lucide-react";
import * as React from "react";
import { Button, ProgressBar } from "@/components/ui/primitives";
import { api, ApiError, subscribeToJob } from "@/lib/api";
import type { JobSnapshot } from "@/lib/types";

const TERMINAL = ["succeeded", "failed", "cancelled"];

export function useJobProgress() {
  const [snapshot, setSnapshot] = React.useState<JobSnapshot | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const cleanupRef = React.useRef<(() => void) | null>(null);
  const doneRef = React.useRef<((snapshot: JobSnapshot) => void) | null>(null);

  const stop = React.useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
  }, []);

  React.useEffect(() => stop, [stop]);

  const follow = React.useCallback(
    (id: string, onDone: (snapshot: JobSnapshot) => void) => {
      stop();
      setJobId(id);
      setSnapshot(null);
      doneRef.current = onDone;

      let finished = false;
      const settle = (next: JobSnapshot) => {
        setSnapshot(next);
        if (finished || !TERMINAL.includes(next.status)) return;
        finished = true;
        stop();
        doneRef.current?.(next);
      };

      const unsubscribe = subscribeToJob(id, settle, settle);
      const timer = window.setInterval(() => {
        api
          .job(id)
          .then(settle)
          .catch(() => {
            /* a single missed poll is not worth surfacing; the stream is still live */
          });
      }, 600);

      cleanupRef.current = () => {
        unsubscribe();
        window.clearInterval(timer);
      };
      // Ask once immediately so the panel is never blank.
      api.job(id).then(settle).catch(() => undefined);
    },
    [stop],
  );

  const cancel = React.useCallback(async () => {
    if (!jobId) return;
    try {
      await api.cancelJob(jobId);
    } catch (cause) {
      if (cause instanceof ApiError) throw cause;
    }
  }, [jobId]);

  const reset = React.useCallback(() => {
    stop();
    setJobId(null);
    setSnapshot(null);
  }, [stop]);

  return { snapshot, jobId, follow, cancel, reset, running: Boolean(jobId) && !snapshot?.status };
}

export function JobProgress({
  snapshot,
  onCancel,
  title = "Building your galaxy",
}: {
  snapshot: JobSnapshot | null;
  onCancel?: () => void;
  title?: string;
}) {
  const status = snapshot?.status ?? "queued";
  const terminal = TERMINAL.includes(status);

  return (
    <div
      className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4"
      aria-live="polite"
      aria-busy={!terminal}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {!terminal && (
            <Loader2 size={14} className="animate-spin text-[var(--color-accent-soft)]" aria-hidden />
          )}
          <p className="text-[13px] font-medium text-[var(--color-ink)]">
            {terminal
              ? status === "succeeded"
                ? "Done"
                : status === "cancelled"
                  ? "Cancelled"
                  : "Import failed"
              : title}
          </p>
        </div>
        {!terminal && onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <XCircle size={13} aria-hidden />
            Cancel
          </Button>
        )}
      </div>

      <div className="mt-3">
        <ProgressBar value={snapshot?.progress ?? 0} label={`Import progress: ${snapshot?.stage ?? "starting"}`} />
      </div>

      <div className="mt-2 flex items-baseline justify-between gap-3">
        <p className="text-[12px] text-[var(--color-ink-2)]">
          {snapshot?.stage || "Queued"}
          {snapshot?.detail ? ` — ${snapshot.detail}` : ""}
        </p>
        <span className="numeral shrink-0 text-[11.5px] text-[var(--color-dim)]">
          {Math.round((snapshot?.progress ?? 0) * 100)}%
        </span>
      </div>

      {snapshot?.error && (
        <p role="alert" className="mt-2 text-[12px] text-[var(--color-broken)]">
          {snapshot.error}
        </p>
      )}
    </div>
  );
}
