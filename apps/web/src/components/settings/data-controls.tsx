"use client";

/**
 * Cache statistics, and the button that deletes everything.
 *
 * Destroying local data is behind a typed confirmation, and the dialog lists what goes
 * rather than asking "are you sure?" — which nobody reads.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Trash2 } from "lucide-react";
import * as React from "react";
import {
  Button,
  Card,
  Dialog,
  ErrorState,
  Field,
  Input,
  KeyValue,
  LoadingBlock,
  SectionTitle,
} from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";

const REMOVED = [
  "Every imported project and its parsed graph",
  "Every scenario, change and applied repair",
  "Every generated report on disk",
  "The append-only decision log",
  "All provider response caches",
  "Every recorded external-request consent",
  "The stored Kimi API key",
];

export function DataControls() {
  const queryClient = useQueryClient();
  const toast = useWorkspace((s) => s.toast);
  const [open, setOpen] = React.useState(false);
  const [confirmation, setConfirmation] = React.useState("");

  const cache = useQuery({
    queryKey: ["cache"],
    queryFn: () => api.cacheStats(),
  });

  const clearCache = useMutation({
    mutationFn: () => api.clearCache(),
    onSuccess: (payload) => {
      queryClient.invalidateQueries({ queryKey: ["cache"] });
      toast("success", `Cleared ${payload?.cleared ?? 0} cached response(s).`);
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not clear the cache."),
  });

  const clearAll = useMutation({
    mutationFn: () => api.clearAllData(),
    onSuccess: (payload) => {
      queryClient.clear();
      setOpen(false);
      setConfirmation("");
      toast("success", payload?.note ?? "All local data has been removed.");
    },
    onError: (cause) =>
      toast("error", cause instanceof ApiError ? cause.message : "Could not clear local data."),
  });

  const stats = cache.data?.cache ?? {};

  return (
    <Card className="p-5">
      <SectionTitle>
        <span className="flex items-center gap-1.5">
          <Database size={13} className="text-[var(--color-dim)]" aria-hidden />
          Data on this machine
        </span>
      </SectionTitle>

      {cache.isLoading ? (
        <LoadingBlock rows={3} label="Loading cache statistics" />
      ) : cache.error ? (
        <ErrorState
          title="Could not read cache statistics"
          detail={cache.error instanceof ApiError ? cache.error.message : String(cache.error)}
          onRetry={() => cache.refetch()}
        />
      ) : (
        <dl className="max-w-md">
          <KeyValue label="Entries">
            <span className="numeral">{stats.entries ?? 0}</span>
          </KeyValue>
          <KeyValue label="Hits">
            <span className="numeral">{stats.hits ?? 0}</span>
          </KeyValue>
          <KeyValue label="Misses">
            <span className="numeral">{stats.misses ?? 0}</span>
          </KeyValue>
          <KeyValue label="Hit rate">
            <span className="numeral">{Math.round((stats.hit_rate ?? 0) * 100)}%</span>
          </KeyValue>
          <KeyValue label="TTL">
            <span className="numeral">{Math.round((stats.ttl_seconds ?? 0) / 3600)}</span> hours
          </KeyValue>
        </dl>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => clearCache.mutate()} loading={clearCache.isPending}>
          Clear caches
        </Button>
        <Button variant="danger" onClick={() => setOpen(true)}>
          <Trash2 size={14} aria-hidden />
          Clear all local data
        </Button>
      </div>

      <p className="mt-2 text-[12px] leading-snug text-[var(--color-muted)]">
        Clearing caches only discards saved provider responses. Nothing about your projects
        changes and the next question simply costs a round trip again.
      </p>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setConfirmation("");
        }}
        title="Clear all local data"
        description="This removes everything API Galaxy has stored on this machine. It cannot be undone and there is no backup."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={confirmation !== "DELETE"}
              loading={clearAll.isPending}
              onClick={() => clearAll.mutate()}
            >
              Delete everything
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <p className="label-eyebrow mb-1.5">What will be removed</p>
            <ul className="space-y-1">
              {REMOVED.map((item) => (
                <li key={item} className="text-[12.5px] text-[var(--color-ink-2)]">
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <Field
            label="Type DELETE to confirm"
            hint="Exactly those six capital letters."
            error={
              confirmation && confirmation !== "DELETE"
                ? "That does not match. Type DELETE in capitals."
                : undefined
            }
          >
            <Input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              placeholder="DELETE"
            />
          </Field>
        </div>
      </Dialog>
    </Card>
  );
}
