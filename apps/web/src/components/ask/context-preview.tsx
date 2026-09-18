"use client";

/**
 * "What gets sent?" — answered before the question is asked, not after.
 *
 * For a local provider this is a courtesy. For an external one it is the whole basis of
 * consent, so the numbers are exact and the sample of allowed identifiers is real text
 * from the payload rather than a reassuring summary.
 */

import { useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import * as React from "react";
import {
  Button,
  Card,
  ErrorState,
  LoadingBlock,
  SectionTitle,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-2.5 py-2">
      <p className="numeral text-[15px] font-semibold text-[var(--color-ink)]">{value}</p>
      <p className="text-[11px] text-[var(--color-dim)]">{label}</p>
    </div>
  );
}

export function ContextPreviewCard({
  projectId,
  question,
}: {
  projectId: string;
  question: string;
}) {
  const [open, setOpen] = React.useState(false);
  const trimmed = question.trim();

  const preview = useQuery({
    queryKey: ["context-preview", projectId, trimmed],
    queryFn: () => api.contextPreview(projectId, trimmed),
    enabled: open && trimmed.length > 0,
  });

  return (
    <Card className="p-3.5">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12.5px] font-medium text-[var(--color-ink)]">What gets sent?</p>
          <p className="text-[11.5px] leading-snug text-[var(--color-dim)]">
            The exact slice of the graph this question is answered from.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          aria-expanded={open}
          disabled={!trimmed}
          onClick={() => setOpen((value) => !value)}
        >
          <Eye size={13} aria-hidden /> {open ? "Hide" : "Show"}
        </Button>
      </div>

      {open && trimmed && (
        <div className="mt-3">
          {preview.isLoading ? (
            <LoadingBlock label="Building the context preview" rows={3} />
          ) : preview.error ? (
            <ErrorState
              title="The preview could not be built"
              detail={(preview.error as ApiError).message}
              correlationId={(preview.error as ApiError).correlationId}
              onRetry={() => void preview.refetch()}
            />
          ) : preview.data ? (
            <ContextPreviewBody data={preview.data} />
          ) : null}
        </div>
      )}
    </Card>
  );
}

export function ContextPreviewBody({ data }: { data: any }) {
  const sample: string[] = data?.sample_ids ?? [];
  return (
    <div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="services" value={data?.services ?? 0} />
        <Stat label="operations" value={data?.operations ?? 0} />
        <Stat label="schemas" value={data?.schemas ?? 0} />
        <Stat label="allowed IDs" value={data?.allowed_ids ?? 0} />
      </div>
      {data?.chunk_label && (
        <p className="mono mt-2 break-all text-[11px] text-[var(--color-dim)]">
          {data.chunk_label}
        </p>
      )}
      {sample.length > 0 && (
        <div className="mt-3">
          <SectionTitle>Sample of the identifiers it may cite</SectionTitle>
          <ul className="mono max-h-[180px] space-y-0.5 overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface-2)] p-2.5 text-[11px] text-[var(--color-muted)]">
            {sample.map((id) => (
              <li key={id} className="break-all">
                {id}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[11.5px] text-[var(--color-dim)]">
            Anything the model cites outside this list is discarded before you see it.
          </p>
        </div>
      )}
    </div>
  );
}
