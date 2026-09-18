/**
 * The typed API client.
 *
 * Every failure from the backend is a problem-details document, so the client throws a
 * single `ApiError` carrying the title, detail and correlation ID. UI code can then show
 * something actionable instead of "request failed".
 */

import type {
  Answer,
  ArenaPayload,
  ExportFormat,
  ExportRecord,
  GraphPayload,
  ImpactPayload,
  JobSnapshot,
  Journey,
  Mission,
  MissionResult,
  NodeDetail,
  Overview,
  Playback,
  ProblemDetails,
  ProjectSummary,
  ProvidersPayload,
  Risk,
  Scenario,
  ValidationResult,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails | null;

  constructor(message: string, status: number, problem: ProblemDetails | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }

  get correlationId(): string {
    return this.problem?.correlation_id ?? "";
  }

  get hint(): string {
    return (this.problem?.hint as string) ?? "";
  }

  /** True when the backend is asking for consent before an external call. */
  get needsConsent(): boolean {
    return this.status === 428;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init?.headers,
      },
    });
  } catch (cause) {
    throw new ApiError(
      "Could not reach the API Galaxy backend. Is it running on port 8099?",
      0,
      null,
    );
  }

  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = (await response.json()) as ProblemDetails;
    } catch {
      /* the body was not JSON; fall through to a generic message */
    }
    throw new ApiError(
      problem?.detail || problem?.title || `Request failed with ${response.status}`,
      response.status,
      problem,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const put = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

const qs = (params: Record<string, string | number | boolean | null | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const api = {
  health: () => request<{ status: string; version: string; projects: number }>("/health"),
  meta: () => request<any>("/meta"),

  // --- projects -------------------------------------------------------------
  listProjects: () => request<{ projects: ProjectSummary[] }>("/projects"),
  getProject: (id: string) => request<any>(`/projects/${id}`),
  deleteProject: (id: string) => del<{ deleted: boolean }>(`/projects/${id}`),
  createDemo: () =>
    post<{ project_id: string; created: boolean; stats: any; enrichment?: string }>(
      "/projects/demo",
    ),
  validateSpec: (content: string, filename: string) =>
    post<ValidationResult>("/specs/validate", { content, filename }),
  importDocuments: (name: string, documents: { content: string; filename: string }[]) =>
    post<{ job_id: string; project_id: string }>("/projects/import", { name, documents }),
  uploadFiles: (files: File[], name = "") => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request<{ job_id: string; project_id: string }>(
      `/projects/upload${qs({ name })}`,
      { method: "POST", body: form },
    );
  },
  overview: (id: string) => request<Overview>(`/projects/${id}/overview`),
  risks: (id: string, severity?: string) =>
    request<{ risks: Risk[]; catalog: any[] }>(`/projects/${id}/risks${qs({ severity })}`),
  diagnostics: (id: string) => request<any>(`/projects/${id}/diagnostics`),

  // --- jobs -----------------------------------------------------------------
  job: (jobId: string) => request<JobSnapshot>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) => post<{ cancelled: boolean }>(`/jobs/${jobId}/cancel`),
  jobEventsUrl: (jobId: string) => `${BASE}/jobs/${jobId}/events`,

  // --- graph ----------------------------------------------------------------
  graph: (
    id: string,
    options: {
      level?: number;
      domain?: string;
      service?: string;
      search?: string;
      include_inferred?: boolean;
      scenario?: string;
      max_nodes?: number;
    } = {},
  ) => request<GraphPayload>(`/projects/${id}/graph${qs(options)}`),
  node: (id: string, nodeId: string, scenario?: string) =>
    request<NodeDetail>(`/projects/${id}/graph/node/${encodeURI(nodeId)}${qs({ scenario })}`),
  edge: (id: string, edgeId: string, scenario?: string) =>
    request<any>(`/projects/${id}/graph/edge/${encodeURI(edgeId)}${qs({ scenario })}`),
  neighbors: (id: string, nodeId: string, depth = 1, scenario?: string) =>
    request<GraphPayload>(
      `/projects/${id}/graph/neighbors/${encodeURI(nodeId)}${qs({ depth, scenario })}`,
    ),
  search: (id: string, q: string) =>
    request<{ query: string; results: any[] }>(`/projects/${id}/graph/search${qs({ q })}`),
  path: (id: string, from: string, to: string, alternatives = 1) =>
    request<any>(`/projects/${id}/graph/path${qs({ from, to, alternatives })}`),
  legend: (id: string) => request<any>(`/projects/${id}/graph/legend`),
  decideEdge: (
    id: string,
    edgeId: string,
    body: { action: "accept" | "reject" | "edit"; label?: string; relation?: string; note?: string },
  ) => post<any>(`/projects/${id}/graph/edges/${encodeURI(edgeId)}/decision`, body),

  // --- journeys -------------------------------------------------------------
  journeys: (id: string, scenario?: string) =>
    request<{ journeys: Journey[] }>(`/projects/${id}/journeys${qs({ scenario })}`),
  playback: (id: string, journeyId: string, scenario?: string) =>
    request<Playback>(
      `/projects/${id}/journeys/${encodeURI(journeyId)}/playback${qs({ scenario })}`,
    ),
  createJourney: (
    id: string,
    body: { name: string; description?: string; steps: { operation_id: string; label?: string; narration?: string }[] },
  ) => post<{ journey: Journey }>(`/projects/${id}/journeys`, body),
  deleteJourney: (id: string, journeyId: string) =>
    del<any>(`/projects/${id}/journeys/${encodeURI(journeyId)}`),

  // --- ask ------------------------------------------------------------------
  starters: (id: string) => request<{ starters: string[] }>(`/projects/${id}/ask/starters`),
  ask: (
    id: string,
    body: { question: string; provider?: string; scenario_id?: string | null; refresh?: boolean },
  ) => post<Answer>(`/projects/${id}/ask`, body),
  contextPreview: (id: string, question: string) =>
    request<any>(`/projects/${id}/ask/context-preview${qs({ question })}`),
  concepts: (id: string) => request<any>(`/projects/${id}/concepts`),

  // --- break lab ------------------------------------------------------------
  changeKinds: (id: string) =>
    request<{ kinds: { id: string; label: string; target_types: string[]; params: any[] }[] }>(
      `/projects/${id}/scenarios/change-kinds`,
    ),
  scenarios: (id: string) => request<{ scenarios: Scenario[] }>(`/projects/${id}/scenarios`),
  createScenario: (id: string, name: string, description = "") =>
    post<{ scenario: Scenario }>(`/projects/${id}/scenarios`, { name, description }),
  addChange: (
    id: string,
    scenarioId: string,
    body: { kind: string; target_id: string; params?: Record<string, any>; label?: string },
  ) => post<ImpactPayload>(`/projects/${id}/scenarios/${scenarioId}/changes`, body),
  undoChange: (id: string, scenarioId: string, index: number) =>
    del<ImpactPayload>(`/projects/${id}/scenarios/${scenarioId}/changes/${index}`),
  impact: (id: string, scenarioId: string) =>
    request<ImpactPayload>(`/projects/${id}/scenarios/${scenarioId}/impact`),
  compare: (id: string, scenarioId: string) =>
    request<any>(`/projects/${id}/scenarios/${scenarioId}/compare`),
  resetScenario: (id: string, scenarioId: string) =>
    post<ImpactPayload>(`/projects/${id}/scenarios/${scenarioId}/reset`),
  deleteScenario: (id: string, scenarioId: string) =>
    del<any>(`/projects/${id}/scenarios/${scenarioId}`),
  proposeRepairs: (id: string, scenarioId: string, provider = "deterministic") =>
    post<{ repairs: any[]; warnings: string[]; deterministic_count: number }>(
      `/projects/${id}/scenarios/${scenarioId}/repairs/propose`,
      { provider },
    ),
  decideRepair: (
    id: string,
    scenarioId: string,
    repairId: string,
    body: { action: "apply" | "reject"; params?: Record<string, any>; title?: string },
  ) =>
    post<any>(
      `/projects/${id}/scenarios/${scenarioId}/repairs/${encodeURI(repairId)}/decision`,
      body,
    ),
  changeSummary: (id: string, scenarioId: string) =>
    request<{ markdown: string; patch: string[]; migration_steps: string[] }>(
      `/projects/${id}/scenarios/${scenarioId}/change-summary`,
    ),
  chaos: (id: string, seed = 0) => post<ImpactPayload>(`/projects/${id}/scenarios/chaos`, { seed }),

  // --- providers ------------------------------------------------------------
  providers: () => request<ProvidersPayload>("/providers/health"),
  updateProviderConfig: (body: Record<string, any>) => put<any>("/providers/config", body),
  setKimiKey: (apiKey: string) => post<any>("/providers/kimi/key", { api_key: apiKey }),
  testProvider: (provider: string) => post<any>(`/providers/${provider}/test`),
  pricing: () => request<any>("/providers/pricing"),
  updatePricing: (body: {
    provider: string;
    input_per_million: number;
    output_per_million: number;
    note?: string;
  }) => put<any>("/providers/pricing", body),
  externalPreview: (id: string) => request<any>(`/projects/${id}/external-preview`),
  setConsent: (id: string, granted: boolean, remember = false) =>
    post<any>(`/projects/${id}/consent`, { granted, remember }),

  // --- arena ----------------------------------------------------------------
  arena: (id: string, providers: string[], domainId?: string) =>
    post<ArenaPayload>(`/projects/${id}/arena`, { providers, domain_id: domainId }),
  arenaDecision: (id: string, body: Record<string, any>) =>
    post<any>(`/projects/${id}/arena/decision`, body),
  decisions: (id: string) => request<{ decisions: any[]; note: string }>(`/projects/${id}/decisions`),

  // --- exports --------------------------------------------------------------
  exportFormats: () => request<{ formats: ExportFormat[]; note: string }>("/exports/formats"),
  createExport: (
    id: string,
    body: {
      format: string;
      scenario_id?: string | null;
      journey_id?: string | null;
      domain_id?: string | null;
      node_ids?: string[];
      scale?: number;
      title?: string;
    },
  ) => post<{ export: ExportRecord; download_url: string; interactive: boolean }>(
    `/projects/${id}/exports`,
    body,
  ),
  listExports: (id: string) => request<{ exports: ExportRecord[] }>(`/projects/${id}/exports`),
  downloadUrl: (exportId: string) => `${BASE}/exports/${exportId}/download`,

  // --- missions -------------------------------------------------------------
  missions: () => request<{ missions: Mission[]; note: string }>("/missions"),
  checkMission: (id: string, missionId: string, attempt: Record<string, any>) =>
    post<MissionResult>(`/projects/${id}/missions/${missionId}/check`, attempt),

  // --- data controls --------------------------------------------------------
  cacheStats: () => request<any>("/cache"),
  clearCache: () => del<any>("/cache"),
  clearAllData: () => del<any>("/data"),
};

/** Subscribe to a job's progress stream. Returns an unsubscribe function. */
export function subscribeToJob(
  jobId: string,
  onProgress: (snapshot: JobSnapshot) => void,
  onDone?: (snapshot: JobSnapshot) => void,
): () => void {
  const source = new EventSource(api.jobEventsUrl(jobId));
  const handle = (event: MessageEvent) => {
    try {
      const snapshot = JSON.parse(event.data) as JobSnapshot;
      onProgress(snapshot);
      if (["succeeded", "failed", "cancelled"].includes(snapshot.status)) {
        onDone?.(snapshot);
        source.close();
      }
    } catch {
      /* a malformed frame is not worth tearing the stream down for */
    }
  };
  source.addEventListener("progress", handle as EventListener);
  source.onerror = () => source.close();
  return () => source.close();
}
