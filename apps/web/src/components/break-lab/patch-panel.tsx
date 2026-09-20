"use client";

/**
 * The scenario as a diff against the documents exactly as they were imported.
 *
 * Break Lab used to end at "here is what breaks". This is the other half: the edit
 * itself, reviewable and applyable, so the answer leaves the tool as work rather than
 * as a note. The diff is textual, so comments and formatting survive and a one-word
 * rename reads as a one-word rename.
 */

import { useQuery } from "@tanstack/react-query";
import { Check, ClipboardCheck, Copy, Download, FileDiff, TriangleAlert } from "lucide-react";
import * as React from "react";
import { Button, Card, LoadingBlock, SectionTitle } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";

/** Colour a unified diff without a syntax-highlighting dependency. */
function DiffBlock({ diff }: { diff: string }) {
  return (
    <pre
      className="scroll-x mono max-h-96 overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-base)] p-3 text-[11.5px] leading-relaxed"
      aria-label="Unified diff of the proposed specification change"
    >
      {diff.split("\n").map((line, index) => {
        // `+++`/`---` are file headers, not insertions — colouring them as changes makes
        // every diff look like it rewrote the whole file.
        const isHeader = line.startsWith("+++") || line.startsWith("---");
        const isHunk = line.startsWith("@@");
        const tone = isHeader
          ? "text-[var(--color-dim)]"
          : isHunk
            ? "text-[var(--color-accent)]"
            : line.startsWith("+")
              ? "text-[var(--color-ok)]"
              : line.startsWith("-")
                ? "text-[var(--color-broken)]"
                : "text-[var(--color-ink-2)]";
        return (
          <div key={index} className={tone}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

export function PatchPanel({
  projectId,
  scenarioId,
  hasChanges,
}: {
  projectId: string;
  scenarioId: string | null;
  hasChanges: boolean;
}) {
  const toast = useWorkspace((s) => s.toast);
  const [copied, setCopied] = React.useState(false);

  const patch = useQuery({
    queryKey: ["scenario-patch", projectId, scenarioId],
    queryFn: () => api.scenarioPatch(projectId, scenarioId!),
    enabled: Boolean(scenarioId) && hasChanges,
  });

  const data = patch.data;

  const copy = async () => {
    if (!data?.patch) return;
    try {
      await navigator.clipboard.writeText(data.patch);
      setCopied(true);
      toast("success", "Patch copied. Apply it with `git apply`.");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast("error", "The browser refused clipboard access. Select the diff and copy it.");
    }
  };

  const download = () => {
    if (!data?.patch) return;
    const blob = new Blob([data.patch], { type: "text/x-patch" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${projectId}-${scenarioId?.split(":").pop() ?? "scenario"}.patch`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card className="p-5">
      <SectionTitle
        action={
          data?.appliable ? (
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={copy}>
                {copied ? <ClipboardCheck size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
                Copy
              </Button>
              <Button variant="secondary" size="sm" onClick={download}>
                <Download size={13} aria-hidden />
                Download .patch
              </Button>
            </div>
          ) : undefined
        }
      >
        <span className="inline-flex items-center gap-1.5">
          <FileDiff size={13} aria-hidden />
          The edit itself
        </span>
      </SectionTitle>

      {!hasChanges ? (
        <p className="text-[12.5px] text-[var(--color-dim)]">
          Add a change to the scenario and the diff against your original documents appears
          here.
        </p>
      ) : patch.isLoading ? (
        <LoadingBlock rows={5} label="Building the diff" />
      ) : patch.isError ? (
        <p className="text-[12.5px] text-[var(--color-broken)]">
          The diff could not be built. The impact analysis above is unaffected.
        </p>
      ) : data ? (
        <>
          <p className="mb-3 text-[12.5px] text-[var(--color-ink-2)]">
            {data.summary}
            {data.appliable && (
              <span className="ml-2 inline-flex items-center gap-1 text-[var(--color-ok)]">
                <Check size={12} aria-hidden />
                re-parses cleanly
              </span>
            )}
          </p>

          {data.files.map((file) => (
            <div key={file.filename} className="mb-4">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <span className="mono text-[12px] text-[var(--color-ink)]">{file.filename}</span>
                {file.applied.map((entry) => (
                  <span
                    key={entry}
                    className="rounded-full border border-[var(--color-line)] px-2 py-0.5 text-[10.5px] text-[var(--color-dim)]"
                  >
                    {entry}
                  </span>
                ))}
              </div>
              {!file.valid && (
                <p
                  role="alert"
                  className="mb-1.5 flex items-start gap-1.5 text-[11.5px] text-[var(--color-broken)]"
                >
                  <TriangleAlert size={12} className="mt-0.5 shrink-0" aria-hidden />
                  <span>
                    This edit does not produce a valid document, so it is shown but not
                    offered for download: {file.validation_errors.join("; ")}
                  </span>
                </p>
              )}
              <DiffBlock diff={file.diff} />
            </div>
          ))}

          {data.skipped.length > 0 && (
            <div className="mt-3 rounded-[var(--radius-sm)] border border-[var(--color-line)] p-3">
              <p className="text-[11.5px] font-medium text-[var(--color-ink-2)]">
                Not in this patch
              </p>
              <ul className="mt-1 space-y-0.5">
                {data.skipped.map((entry) => (
                  <li key={entry} className="text-[11.5px] text-[var(--color-dim)]">
                    {entry}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.warnings.map((warning) => (
            <p key={warning} className="mt-2 text-[11.5px] text-[var(--color-degraded)]">
              {warning}
            </p>
          ))}

          {data.appliable && (
            <p className="mt-3 text-[11.5px] text-[var(--color-dim)]">
              <span className="mono">{data.apply_command}</span> — {data.caveat}
            </p>
          )}
        </>
      ) : null}
    </Card>
  );
}
