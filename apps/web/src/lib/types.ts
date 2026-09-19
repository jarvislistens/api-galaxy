/**
 * Shapes returned by the API Galaxy backend.
 *
 * These mirror the Pydantic contracts in `apps/api/api_galaxy/contracts`. They are
 * hand-written rather than generated because the surface is small and stable, and a
 * generator would be one more thing that has to be running for the app to build.
 * `packages/contracts` holds the JSON Schemas both sides are checked against.
 */

export type SourceKind =
  | "specification"
  | "deterministic_rule"
  | "bundled_analysis"
  | "ai_inference"
  | "user_edit"
  | "scenario";

export type Acceptance = "observed" | "proposed" | "accepted" | "rejected" | "superseded";

export type Stroke = "solid" | "dashed" | "dotted";

export type NodeType =
  | "Estate" | "Domain" | "Service" | "Server" | "APIOperation" | "Endpoint"
  | "Schema" | "Field" | "SecurityScheme" | "BusinessEntity" | "Capability"
  | "Journey" | "JourneyStep" | "Risk" | "Scenario" | "Change" | "Repair" | "Evidence";

export interface Provenance {
  source_kind: SourceKind;
  explanation: string;
  source_file?: string | null;
  source_pointer?: string | null;
  rule_id?: string | null;
  confidence?: number | null;
  provider?: string | null;
  model?: string | null;
  prompt_template_version?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  id: string;
  source_file: string;
  pointer: string;
  excerpt: string;
  label: string;
}

export interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  project_id: string;
  description: string;
  acceptance: Acceptance;
  provenance: Provenance;
  attrs: Record<string, any>;
  evidence: Evidence[];
  tags: string[];
  zoom?: string;
  is_fact?: boolean;
}

export interface GraphEdge {
  id: string;
  type: string;
  source: string;
  target: string;
  label: string;
  acceptance: Acceptance;
  provenance: Provenance;
  attrs: Record<string, any>;
  evidence: Evidence[];
  stroke?: Stroke;
  is_fact?: boolean;
}

export interface GraphStats {
  nodes: number;
  edges: number;
  by_node_type: Record<string, number>;
  by_edge_type: Record<string, number>;
  observed_edges: number;
  inferred_edges: number;
  user_edges: number;
  accepted_inferences: number;
  services: number;
  operations: number;
  schemas: number;
  fields: number;
  domains: number;
  journeys: number;
  risks: number;
  entities: number;
  capabilities: number;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  truncation_reason: string;
  stats: GraphStats;
  level?: number;
  scenario_id?: string | null;
}

export type RiskSeverity = "high" | "medium" | "low" | "info";

export interface Risk {
  id: string;
  rule_id: string;
  severity: RiskSeverity;
  category: string;
  title: string;
  description: string;
  recommendation: string;
  heuristic: boolean;
  node_ids: string[];
  edge_ids: string[];
  evidence: Evidence[];
  provenance: Provenance;
}

export interface JourneyStep {
  id: string;
  order: number;
  label: string;
  narration: string;
  service_id?: string | null;
  operation_id?: string | null;
  schema_ids: string[];
  node_ids: string[];
  evidence: Evidence[];
  technical_detail: string;
  deprecated: boolean;
}

export interface JourneyValidation {
  journey_id: string;
  journey_name: string;
  ok: boolean;
  broken_steps: string[];
  degraded_steps: string[];
  steps: { step_id: string; ok: boolean; reasons: string[] }[];
  summary: string;
}

export interface Journey {
  id: string;
  name: string;
  description: string;
  steps: JourneyStep[];
  domain_ids: string[];
  provenance: Provenance;
  editable: boolean;
  validation?: JourneyValidation;
  services?: string[];
}

export interface PlaybackFrame {
  order: number;
  step_id: string;
  label: string;
  narration: string;
  technical_detail: string;
  operation_id?: string | null;
  service_id?: string | null;
  service?: string | null;
  method?: string | null;
  path?: string | null;
  schema_ids: string[];
  schemas: string[];
  highlight_nodes: string[];
  highlight_edges: string[];
  trail: string[];
  deprecated: boolean;
  ok: boolean;
  problems: string[];
  evidence: Evidence[];
}

export interface Playback {
  journey: { id: string; name: string; description: string; source: SourceKind; explanation: string };
  frames: PlaybackFrame[];
  validation: JourneyValidation;
  scenario_id?: string | null;
}

export interface Overview {
  project_id: string;
  project_name: string;
  counts: Record<string, number>;
  domains: {
    id: string;
    name: string;
    description: string;
    services: string[];
    service_ids: string[];
    operation_count: number;
    risk_count: number;
  }[];
  journeys: {
    id: string;
    name: string;
    description: string;
    steps: number;
    services: string[];
    source: SourceKind;
    has_deprecated_step: boolean;
  }[];
  top_risks: Risk[];
  ambiguities: { id: string; title: string; description: string; node_ids: string[]; kind: string }[];
  parse_coverage: Record<string, any>;
  enrichment: { label: string; warnings: string[]; is_bundled: boolean };
  derivation: { step: string; detail: string }[];
}

export interface AnswerEvidenceItem {
  node_id: string;
  label: string;
  type: string;
  why: string;
  is_fact: boolean;
  source: string[];
  service?: string | null;
}

export interface Answer {
  question: string;
  provider: string;
  model: string;
  answer: string;
  technical_explanation: string;
  highlighted_node_ids: string[];
  highlighted_edge_ids: string[];
  path: string[];
  path_labels: string[];
  evidence: AnswerEvidenceItem[];
  inference_note: string;
  fact_vs_inference: { facts: number; inferences: number };
  confidence: number;
  coverage: number;
  grounded: boolean;
  dropped_references: string[];
  latency_ms: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached: boolean;
  warning?: string;
}

export type ImpactStatus = "broken" | "degraded" | "potentially_affected" | "unaffected";

export interface ImpactItem {
  node_id: string;
  node_label: string;
  node_type: string;
  status: ImpactStatus;
  distance: number;
  reason: string;
  chain: string[];
  chain_labels: string[];
  /**
   * The edge type crossed at each hop, parallel to `chain` and one entry shorter —
   * n nodes are joined by n-1 relationships. This is what separates "consumes the
   * changed contract" from "is a suggested alias of it", which distance alone cannot.
   */
  via: string[];
}

export interface Change {
  id: string;
  kind: string;
  target_id: string;
  params: Record<string, any>;
  label: string;
  created_at: string;
}

export interface Repair {
  id: string;
  title: string;
  rationale: string;
  kind: string;
  target_ids: string[];
  params: Record<string, any>;
  confidence?: number | null;
  deterministic: boolean;
  status: "proposed" | "accepted" | "rejected" | "applied";
  provenance: Provenance;
  patch: string[];
  migration_steps: string[];
}

export interface Scenario {
  id: string;
  project_id: string;
  name: string;
  description: string;
  changes: Change[];
  repairs: Repair[];
  created_at: string;
  updated_at: string;
  change_count?: number;
  applied_repairs?: number;
}

export interface ImpactPayload {
  scenario: Scenario;
  impact: {
    scenario_id: string;
    changes: Change[];
    items: ImpactItem[];
    affected_journeys: JourneyValidation[];
    counts: Record<string, number>;
    assumptions: string[];
    limitations: string[];
    added_nodes: string[];
    removed_nodes: string[];
    changed_nodes: string[];
  };
  shockwave: ImpactItem[];
  journeys: JourneyValidation[];
  all_journeys: JourneyValidation[];
  changed_nodes: { id: string; label: string }[];
  hidden_origin_token?: string;
  candidates?: { id: string; label: string; service?: string }[];
}

export interface ProviderHealth {
  kind: "deterministic" | "ollama" | "kimi";
  status: "ready" | "not_configured" | "unreachable" | "disabled" | "error";
  model?: string | null;
  base_url?: string | null;
  detail: string;
  setup_hint: string;
  external: boolean;
  latency_ms?: number | null;
  available_models: string[];
  ready: boolean;
}

export interface ProvidersPayload {
  providers: ProviderHealth[];
  settings: Record<string, any>;
  kimi_key_configured: boolean;
  prompt_template_version: string;
  modes: { id: string; label: string; detail: string; provider: string }[];
}

export interface ArenaRelation {
  source_id: string;
  target_id: string;
  relation: string;
  providers: string[];
  confidences: Record<string, number>;
  rationales: Record<string, string>;
  verdict: string;
  source_label?: string;
  target_label?: string;
}

export interface ArenaMetrics {
  provider: string;
  model: string;
  ok: boolean;
  error: string;
  latency_ms: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  estimated_cost_usd?: number | null;
  valid_structured_output: boolean;
  retries: number;
  entities: number;
  relations: number;
  aliases: number;
  domains: number;
  risks: number;
  hallucinated_references: number;
  rationale: string;
}

export interface ArenaPayload {
  project_id: string;
  task: string;
  metrics: ArenaMetrics[];
  consensus: ArenaRelation[];
  only_a: ArenaRelation[];
  only_b: ArenaRelation[];
  conflicts: ArenaRelation[];
  alias_agreement: Record<string, any>;
  domain_agreement: Record<string, any>;
  notes: string[];
  pricing_disclaimer: string;
  prompt_template_version: string;
}

export interface ExportFormat {
  id: string;
  label: string;
  extension: string;
  media_type: string;
  description: string;
  interactive: boolean;
  available: boolean;
  unavailable_reason: string;
}

export interface ExportRecord {
  id: string;
  project_id: string;
  format: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  scope: string;
  created_at: string;
  download_url?: string;
}

export interface Mission {
  id: string;
  title: string;
  tagline: string;
  brief: string;
  difficulty: "gentle" | "tricky" | "hard";
  estimated_seconds: number;
  answer_kind: string;
  hints: string[];
  where: string;
  points: number;
  teaches: string;
}

export interface MissionResult {
  mission_id: string;
  correct: boolean;
  message: string;
  reveal: string[];
  reveal_labels: string[];
  score: number;
  max_score: number;
  teaches: string;
  share_text: string;
}

export interface JobSnapshot {
  id: string;
  kind: string;
  project_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  stage: string;
  detail: string;
  error: string;
  created_at: string;
  result: any;
}

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  source_kind: string;
  spec_fingerprint: string;
  app_version: string;
  enrichment_label: string;
  is_demo: boolean;
  stats: Partial<GraphStats>;
  created_at: string | null;
  updated_at: string | null;
}

export interface ValidationResult {
  valid: boolean;
  kind: string;
  format: string;
  title: string;
  version: string;
  counts: Record<string, number>;
  diagnostics: {
    level: "error" | "warning" | "info";
    code: string;
    message: string;
    file: string;
    pointer: string;
    hint: string;
  }[];
  error: { message: string; line?: number | null; column?: number | null; field_path?: string | null; hint: string } | null;
  preview: {
    service: string;
    operations: { id: string; method: string; path: string; summary: string; deprecated: boolean }[];
    schemas: string[];
  } | null;
}

export interface NodeDetail {
  node: GraphNode;
  evidence: Evidence[];
  incoming: (GraphEdge & { other: string; other_id: string; other_type: string })[];
  outgoing: (GraphEdge & { other: string; other_id: string; other_type: string })[];
  risks: GraphNode[];
  dependents: { id: string; label: string; type: string; distance: number }[];
  aliases: {
    id: string;
    label: string;
    name: string;
    service?: string;
    confidence?: number;
    acceptance: Acceptance;
    edge_id: string;
    rationale: string;
    source: SourceKind;
  }[];
}

export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  correlation_id: string;
  [key: string]: any;
}
