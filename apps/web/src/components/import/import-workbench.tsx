"use client";

/**
 * The import screen.
 *
 * Every path here validates before it imports. A specification that will not parse is a
 * fact you want in half a second with a line number, not ninety seconds later as a failed
 * background job — so `POST /specs/validate` runs on the client's schedule (on drop, and
 * on a 500 ms debounce while typing) and the import button stays inert until something is
 * actually parseable.
 */

import {
  ArrowLeft,
  ArrowRight,
  FileJson,
  Link2Off,
  Lock,
  Sparkles,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { FileIntake } from "@/components/import/file-intake";
import { JobProgress, useJobProgress } from "@/components/import/job-progress";
import { ValidationReport } from "@/components/import/validation-report";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  Field,
  InfoNote,
  Input,
  SectionTitle,
  Tab,
  TabPanel,
  Tabs,
  TabsBar,
  cx,
} from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { ValidationResult } from "@/lib/types";

const SpecEditor = dynamic(() => import("@/components/import/spec-editor"), {
  ssr: false,
  loading: () => (
    <div className="skeleton h-[360px] w-full rounded-[var(--radius-md)]" aria-label="Loading editor" />
  ),
});

interface Entry {
  id: string;
  file: File;
  name: string;
  pending: boolean;
  result: ValidationResult | null;
  failure: string | null;
}

const SPEC_ACCEPT = ".json,.yaml,.yml";
const POSTMAN_ACCEPT = ".json";
/** `meta.limits.max_upload_bytes` on the backend. Shown so a rejection is never a surprise. */
const MAX_UPLOAD_MB = 12;

function detectFormat(text: string): "json" | "yaml" {
  return text.trimStart().startsWith("{") || text.trimStart().startsWith("[") ? "json" : "yaml";
}

export function ImportWorkbench() {
  const router = useRouter();
  const [tab, setTab] = React.useState("files");
  const [name, setName] = React.useState("");
  const [entries, setEntries] = React.useState<Entry[]>([]);
  const [paste, setPaste] = React.useState("");
  const [pasteResult, setPasteResult] = React.useState<ValidationResult | null>(null);
  const [pasteChecking, setPasteChecking] = React.useState(false);
  const [pasteFailure, setPasteFailure] = React.useState<string | null>(null);
  const [submitError, setSubmitError] = React.useState<ApiError | Error | null>(null);
  const [demoLoading, setDemoLoading] = React.useState(false);
  const [starting, setStarting] = React.useState(false);

  const job = useJobProgress();

  /* ------------------------------------------------------------------ files */

  const addFiles = React.useCallback(async (files: File[]) => {
    setSubmitError(null);
    const staged: Entry[] = files.map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 7)}`,
      file,
      name: file.name,
      pending: true,
      result: null,
      failure: null,
    }));
    setEntries((current) => [...current, ...staged]);

    await Promise.all(
      staged.map(async (entry) => {
        if (entry.file.size > MAX_UPLOAD_MB * 1024 * 1024) {
          setEntries((current) =>
            current.map((item) =>
              item.id === entry.id
                ? {
                    ...item,
                    pending: false,
                    failure: `This file is larger than the ${MAX_UPLOAD_MB} MB limit the backend accepts.`,
                  }
                : item,
            ),
          );
          return;
        }
        try {
          const content = await entry.file.text();
          const result = await api.validateSpec(content, entry.file.name);
          setEntries((current) =>
            current.map((item) =>
              item.id === entry.id ? { ...item, pending: false, result } : item,
            ),
          );
        } catch (cause) {
          setEntries((current) =>
            current.map((item) =>
              item.id === entry.id
                ? {
                    ...item,
                    pending: false,
                    failure:
                      cause instanceof ApiError
                        ? cause.message
                        : "Could not read this file as text.",
                  }
                : item,
            ),
          );
        }
      }),
    );
  }, []);

  const removeEntry = React.useCallback((id: string) => {
    setEntries((current) => current.filter((entry) => entry.id !== id));
  }, []);

  const validEntries = entries.filter((entry) => entry.result?.valid);
  const invalidEntries = entries.filter((entry) => !entry.pending && !entry.result?.valid);
  const stillChecking = entries.some((entry) => entry.pending);

  /* ------------------------------------------------------------------ paste */

  React.useEffect(() => {
    const text = paste.trim();
    if (!text) {
      setPasteResult(null);
      setPasteFailure(null);
      setPasteChecking(false);
      return;
    }
    setPasteChecking(true);
    const handle = window.setTimeout(() => {
      const filename = detectFormat(text) === "json" ? "pasted-spec.json" : "pasted-spec.yaml";
      api
        .validateSpec(text, filename)
        .then((result) => {
          setPasteResult(result);
          setPasteFailure(null);
        })
        .catch((cause) => {
          setPasteResult(null);
          setPasteFailure(
            cause instanceof ApiError ? cause.message : "Could not reach the validator.",
          );
        })
        .finally(() => setPasteChecking(false));
    }, 500);
    return () => window.clearTimeout(handle);
  }, [paste]);

  /* ----------------------------------------------------------------- submit */

  const finish = React.useCallback(
    (projectId: string) => (snapshot: { status: string; result: any }) => {
      if (snapshot.status === "succeeded") {
        router.push(`/workspace/${snapshot.result?.project_id ?? projectId}`);
      }
    },
    [router],
  );

  const importFiles = React.useCallback(async () => {
    if (!validEntries.length) return;
    setStarting(true);
    setSubmitError(null);
    try {
      const response = await api.uploadFiles(
        validEntries.map((entry) => entry.file),
        name.trim(),
      );
      job.follow(response.job_id, finish(response.project_id));
    } catch (cause) {
      setSubmitError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setStarting(false);
    }
  }, [validEntries, name, job, finish]);

  const importPaste = React.useCallback(async () => {
    const text = paste.trim();
    if (!text || !pasteResult?.valid) return;
    setStarting(true);
    setSubmitError(null);
    try {
      const filename = pasteResult.format === "json" ? "pasted-spec.json" : "pasted-spec.yaml";
      const response = await api.importDocuments(name.trim() || pasteResult.title || "Pasted API", [
        { content: text, filename },
      ]);
      job.follow(response.job_id, finish(response.project_id));
    } catch (cause) {
      setSubmitError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setStarting(false);
    }
  }, [paste, pasteResult, name, job, finish]);

  const openDemo = React.useCallback(async () => {
    setDemoLoading(true);
    setSubmitError(null);
    try {
      const result = await api.createDemo();
      router.push(`/workspace/${result.project_id}`);
    } catch (cause) {
      setSubmitError(cause instanceof Error ? cause : new Error(String(cause)));
      setDemoLoading(false);
    }
  }, [router]);

  const busy = Boolean(job.jobId) && !["succeeded", "failed", "cancelled"].includes(job.snapshot?.status ?? "");

  /* ------------------------------------------------------------------- view */

  return (
    <main id="main" className="min-h-[100svh] bg-[var(--color-base)]">
      <header className="sticky top-0 z-20 border-b border-[var(--color-line)] bg-[var(--color-base)]/92 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
          <Link
            href="/"
            className="flex items-center gap-2 text-[13px] text-[var(--color-ink-2)] transition-colors hover:text-[var(--color-ink)]"
          >
            <ArrowLeft size={14} aria-hidden />
            <span className="font-semibold tracking-tight">API Galaxy</span>
          </Link>
          <Badge tone="accent" icon={<Lock size={11} aria-hidden />}>
            Parsed on this machine · nothing is sent anywhere
          </Badge>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 pb-24 pt-10">
        <p className="label-eyebrow">Import</p>
        <h1 className="mt-2 text-balance text-[clamp(1.9rem,4.2vw,2.75rem)] font-semibold leading-tight tracking-[-0.03em]">
          Build your API Galaxy
        </h1>
        <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-[var(--color-muted)]">
          Drop one specification or your whole estate. Every document is parsed and checked
          before anything is imported, so a file that will not load tells you which line broke
          it rather than failing silently later.
        </p>

        <div className="mt-9 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          {/* ------------------------------------------------------- main column */}
          <div className="min-w-0 space-y-5">
            <Card className="p-5">
              <Field
                label="Project name"
                hint="Optional. Leave it blank and the estate is named from the first document."
              >
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="NovaCart production estate"
                  disabled={busy}
                />
              </Field>
            </Card>

            <Tabs value={tab} onValueChange={setTab}>
              <TabsBar aria-label="How to bring your specification in">
                <Tab value="files">Upload files</Tab>
                <Tab value="paste">Paste</Tab>
                <Tab value="postman">Postman</Tab>
                <Tab value="url">Specification URL</Tab>
              </TabsBar>

              {/* ------------------------------------------------------- files */}
              <TabPanel value="files" className="mt-4 space-y-4 focus-visible:outline-none">
                <FileIntake
                  id="spec-files"
                  accept={SPEC_ACCEPT}
                  disabled={busy}
                  onFiles={addFiles}
                  headline="Drop OpenAPI files here, or choose them"
                  help={
                    <>
                      .json, .yaml or .yml · OpenAPI 3.0 and 3.1 · several files at once
                      <br />
                      Up to {MAX_UPLOAD_MB} MB each
                    </>
                  }
                />
                <EntryList
                  entries={entries}
                  onRemove={removeEntry}
                  disabled={busy}
                />
              </TabPanel>

              {/* ------------------------------------------------------- paste */}
              <TabPanel value="paste" className="mt-4 space-y-4 focus-visible:outline-none">
                <div>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <label
                      htmlFor="paste-editor"
                      className="text-[12.5px] font-medium text-[var(--color-ink-2)]"
                    >
                      Paste an OpenAPI document
                    </label>
                    <span className="text-[11.5px] text-[var(--color-dim)]">
                      Detected as {detectFormat(paste).toUpperCase()} ·{" "}
                      {pasteChecking ? "checking…" : "checked as you type"}
                    </span>
                  </div>
                  <div id="paste-editor">
                    <SpecEditor
                      value={paste}
                      onChange={setPaste}
                      language={pasteResult?.format === "json" ? "json" : detectFormat(paste)}
                      ariaLabel="Specification source"
                      errorLine={pasteResult?.error?.line ?? null}
                    />
                  </div>
                </div>

                <div aria-live="polite">
                  {paste.trim() ? (
                    <ul className="space-y-3">
                      <ValidationReport
                        filename={
                          (pasteResult?.format ?? detectFormat(paste)) === "json"
                            ? "pasted-spec.json"
                            : "pasted-spec.yaml"
                        }
                        result={pasteResult}
                        pending={pasteChecking && !pasteResult}
                        failure={pasteFailure}
                      />
                    </ul>
                  ) : (
                    <InfoNote>
                      Nothing pasted yet. The document is validated 500 ms after you stop
                      typing — no import happens until you ask for one.
                    </InfoNote>
                  )}
                </div>
              </TabPanel>

              {/* ----------------------------------------------------- postman */}
              <TabPanel value="postman" className="mt-4 space-y-4 focus-visible:outline-none">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="degraded">Beta</Badge>
                  <p className="text-[12.5px] text-[var(--color-muted)]">
                    Paths, methods and request names are recovered. Schemas, field types and
                    the relationships between them are not — a collection does not contain them.
                  </p>
                </div>
                <FileIntake
                  id="postman-files"
                  accept={POSTMAN_ACCEPT}
                  disabled={busy}
                  onFiles={addFiles}
                  headline="Drop a Postman collection export"
                  help="Collection v2.0 or v2.1 (.json). The backend detects the format on its own."
                />
                <EntryList entries={entries} onRemove={removeEntry} disabled={busy} />
              </TabPanel>

              {/* --------------------------------------------------------- url */}
              <TabPanel value="url" className="mt-4 focus-visible:outline-none">
                <Card className="p-5">
                  <div className="flex items-start gap-3">
                    <Link2Off size={17} className="mt-[2px] shrink-0 text-[var(--color-dim)]" aria-hidden />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-[14px] font-semibold text-[var(--color-ink)]">
                          Importing from a URL is not available in this build
                        </h2>
                        <Badge tone="neutral">Disabled</Badge>
                      </div>
                      <p className="mt-2 text-[13px] leading-relaxed text-[var(--color-muted)]">
                        Fetching a specification by URL means the backend makes an outbound
                        request on your behalf, which is a server-side request forgery risk
                        unless the target is checked against private address ranges, redirects
                        and DNS rebinding. That check is not shipped here, so the endpoint does
                        not exist — there is nothing for this form to call.
                      </p>
                      <p className="mt-2 text-[13px] leading-relaxed text-[var(--color-muted)]">
                        Download the document yourself and use{" "}
                        <button
                          type="button"
                          onClick={() => setTab("files")}
                          className="text-[var(--color-accent-soft)] underline underline-offset-2"
                        >
                          Upload files
                        </button>{" "}
                        or{" "}
                        <button
                          type="button"
                          onClick={() => setTab("paste")}
                          className="text-[var(--color-accent-soft)] underline underline-offset-2"
                        >
                          Paste
                        </button>
                        .
                      </p>
                      <div className="mt-4 flex gap-2 opacity-45">
                        <Input
                          value=""
                          readOnly
                          disabled
                          aria-label="Specification URL (not available in this build)"
                          placeholder="https://example.com/openapi.yaml"
                        />
                        <Button disabled>Fetch</Button>
                      </div>
                    </div>
                  </div>
                </Card>
              </TabPanel>
            </Tabs>

            {/* ------------------------------------------------------- actions */}
            {submitError && (
              <ErrorState
                title="Could not start the import"
                detail={submitError.message}
                hint={submitError instanceof ApiError ? submitError.hint : undefined}
                correlationId={
                  submitError instanceof ApiError ? submitError.correlationId : undefined
                }
              />
            )}

            {job.jobId && (
              <JobProgress
                snapshot={job.snapshot}
                onCancel={() => {
                  void job.cancel();
                }}
              />
            )}

            {job.snapshot?.status === "failed" && (
              <ErrorState
                title="The import failed"
                detail={job.snapshot.error || "The backend did not say why."}
                onRetry={() => job.reset()}
              />
            )}

            {!busy && (
              <div className="flex flex-wrap items-center gap-3">
                {tab === "paste" ? (
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={importPaste}
                    loading={starting}
                    disabled={!pasteResult?.valid}
                  >
                    Import this specification
                    <ArrowRight size={15} aria-hidden />
                  </Button>
                ) : tab === "url" ? null : (
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={importFiles}
                    loading={starting}
                    disabled={!validEntries.length || stillChecking}
                  >
                    Import {validEntries.length || ""}{" "}
                    {validEntries.length === 1 ? "document" : "documents"}
                    <ArrowRight size={15} aria-hidden />
                  </Button>
                )}
                {tab !== "paste" && tab !== "url" && invalidEntries.length > 0 && (
                  <p className="text-[12.5px] text-[var(--color-degraded)]">
                    {invalidEntries.length} file{invalidEntries.length === 1 ? "" : "s"} will be
                    skipped — fix or remove {invalidEntries.length === 1 ? "it" : "them"} to
                    include {invalidEntries.length === 1 ? "it" : "them"}.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* --------------------------------------------------------- sidebar */}
          <aside className="space-y-4">
            <Card raised className="p-5">
              <SectionTitle>No specification to hand?</SectionTitle>
              <p className="text-[13px] leading-relaxed text-[var(--color-muted)]">
                The bundled NovaCart estate is seven services, 32 operations and 366 graph
                nodes. It needs no model, no key and no internet.
              </p>
              <Button
                variant="primary"
                className="mt-4 w-full"
                onClick={openDemo}
                loading={demoLoading}
                disabled={busy}
              >
                <Sparkles size={14} aria-hidden />
                Use demo estate
              </Button>
            </Card>

            <Card className="p-5">
              <SectionTitle>What happens next</SectionTitle>
              <ol className="space-y-2.5 text-[12.5px] leading-snug text-[var(--color-muted)]">
                {[
                  "Each document is parsed deterministically — no model is involved.",
                  "Services, operations, schemas and fields become graph nodes with a source file and JSON Pointer each.",
                  "Deterministic rules derive domains, journeys, aliases and findings, all labelled as inference.",
                  "You land in the workspace with the graph already built.",
                ].map((step, index) => (
                  <li key={step} className="flex gap-2.5">
                    <span className="numeral mt-[1px] shrink-0 text-[11px] text-[var(--color-dim)]">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </Card>

            <Card className="p-5">
              <SectionTitle>Accepted input</SectionTitle>
              <ul className="space-y-2 text-[12.5px] text-[var(--color-muted)]">
                <li className="flex items-start gap-2">
                  <FileJson size={13} className="mt-[3px] shrink-0 text-[var(--color-dim)]" aria-hidden />
                  <span>OpenAPI 3.0 / 3.1 in JSON or YAML</span>
                </li>
                <li className="flex items-start gap-2">
                  <FileJson size={13} className="mt-[3px] shrink-0 text-[var(--color-dim)]" aria-hidden />
                  <span>Postman collection v2.x — beta, paths and methods only</span>
                </li>
                <li className="flex items-start gap-2">
                  <Link2Off size={13} className="mt-[3px] shrink-0 text-[var(--color-dim)]" aria-hidden />
                  <span>URL fetching is disabled in this build</span>
                </li>
              </ul>
              <p className="mt-3 text-[11.5px] leading-snug text-[var(--color-dim)]">
                Remote <span className="mono">$ref</span>s are not resolved either, for the same
                reason.
              </p>
            </Card>
          </aside>
        </div>
      </div>
    </main>
  );
}

function EntryList({
  entries,
  onRemove,
  disabled,
}: {
  entries: Entry[];
  onRemove: (id: string) => void;
  disabled?: boolean;
}) {
  if (!entries.length) {
    return (
      <p className="text-[12.5px] text-[var(--color-dim)]">
        Nothing staged yet. Files are checked the moment they land and are not imported until
        you press the button.
      </p>
    );
  }
  return (
    <div aria-live="polite">
      <p className="label-eyebrow mb-2">
        {entries.length} document{entries.length === 1 ? "" : "s"} staged
      </p>
      <ul className={cx("space-y-3", disabled && "pointer-events-none opacity-60")}>
        {entries.map((entry) => (
          <ValidationReport
            key={entry.id}
            filename={entry.name}
            result={entry.result}
            pending={entry.pending}
            failure={entry.failure}
            onRemove={() => onRemove(entry.id)}
          />
        ))}
      </ul>
    </div>
  );
}
