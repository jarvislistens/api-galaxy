# API Galaxy — Implementation Plan

> Drop your API. Watch it come alive. Ask how it works. Break it before production does.

This document is the working checklist for building API Galaxy. It records the plan,
the decisions taken autonomously, and the state of each milestone.

## 0. Environment (inspected 2026-09-19)

| Thing | Finding | Consequence |
| --- | --- | --- |
| Node | v25.9.0 / npm 11.12.1 | Next.js 15 fine |
| Python | 3.11, 3.12, 3.13, 3.14 present; `uv` installed | Backend pinned to **3.12** (3.14 wheels still patchy) |
| Ollama | installed, has `qwen3:4b`, `moondream` | Default local model = `qwen3:4b` with `think:false` |
| Disk | **6.7 GB free** | Be frugal: no Electron, no heavy ML deps, Playwright chromium only |
| Git | 2.39.5, fresh repo | — |

## 1. Locked decisions (ADRs in `docs/architecture/`)

1. **Graph library — Cytoscape.js** over React Flow. Reasons: built-in `fcose`/`dagre`/
   `concentric` layouts, compound (parent) nodes for semantic zoom levels, headless mode
   so the *same* engine renders inside the exported HTML report, and native SVG/PNG
   export. React Flow needs custom layout wiring and has no headless export path.
   → `docs/architecture/adr-001-graph-library.md`
2. **Provider abstraction** — `SemanticProvider` protocol with `Deterministic`, `Ollama`,
   `Kimi` implementations plus a `ComparisonService`. Deterministic is always available
   so the demo never depends on a model. → `adr-002-provider-abstraction.md`
3. **Provenance** — every node/edge carries a `Provenance` record; facts and inferences
   live in the same graph but are never merged. → `adr-003-provenance.md`
4. **Exports** — one canonical `ReportBundle` built server-side; each exporter is a pure
   function of that bundle. The interactive HTML export embeds a pre-built, dependency-free
   `report-runtime` bundle (no CDN). → `adr-004-exports.md`
5. **Design system lives inside `apps/web`** rather than `packages/design-system`.
   Concrete reason: exactly one consumer, and a separate package would add a build step
   (and ~100 MB of duplicated tooling) for no benefit on a disk-constrained machine.
   The report runtime ships its own minimal CSS derived from the same tokens file.
6. **Storage** — SQLite via SQLAlchemy for projects/scenarios/decisions/jobs/settings;
   graph snapshots as JSON documents on disk under the app data dir. NetworkX for
   algorithms behind a `GraphRepository` interface.
7. **Secrets** — external API keys are stored in the OS keychain when `keyring` is
   available, otherwise session-only memory. Never written to SQLite or logs.

## 2. Milestones

- [x] **M0 Bootstrap** — repo shape, tooling, Makefile, env example, plan.
- [x] **M1 Contracts** — node/edge/provenance models, ID scheme, JSON Schemas, TS types.
- [x] **M2 Sample estate** — NovaCart: 7 OpenAPI specs + expected ontology/journeys/risks
      + postman collection + demo script, with the 9 required teaching defects.
- [x] **M3 Parser** — OpenAPI 3.0/3.1, YAML, safe `$ref`, cycles, normalization, diagnostics.
- [x] **M4 Graph engine** — build, traversal, cycles, components, neighborhood, diff,
      impact propagation, journey validation, alias clusters, query guards.
- [x] **M5 Deterministic analysis** — 14 risk rules, PII dictionaries, pagination/error
      envelope consistency, breaking-change detection.
- [x] **M6 Providers** — Deterministic / Ollama / Kimi, strict JSON schema validation,
      bounded retries, ID whitelisting, caching, sanitizer + consent.
- [x] **M7 API** — FastAPI, SQLite, jobs, SSE progress, problem-details errors.
- [x] **M8 Exports** — HTML, PDF, SVG, PNG, Mermaid, JSON-LD, GraphML, CSV, Markdown.
- [x] **M9 Web** — landing, import, workspace shell, Overview, Journeys, Galaxy, Ask,
      Break Lab, Repair, Model Arena, Missions, Reports, Settings.
- [x] **M10 Tests** — pytest unit + integration, Playwright e2e, lint, types, prod build.
- [x] **M11 Docs** — README, privacy, model evaluation, demo guide, ADRs, CONTRIBUTING,
      SECURITY, LICENSE.

## 3. Sample estate defects (deliberate, documented)

| # | Defect | Where |
| --- | --- | --- |
| 1 | `customer_id` / `cust_no` / `party_key` are the same concept | customer, order, payment |
| 2 | Weakly secured endpoint exposes sensitive data | `GET /public/customers/{id}/summary` (customer-api) |
| 3 | Checkout depends on a customer identifier through >1 service | cart → order → payment |
| 4 | Inconsistent error envelopes | `Error` (customer/catalog) vs `ProblemResponse` (order/payment) |
| 5 | Field changes type across boundaries | `amount` string(decimal) in payment, number in order |
| 6 | Deprecated endpoint still in a journey | `POST /carts/{cartId}/checkout` (cart-api) |
| 7 | Suspicious circular dependency | order ↔ inventory (reserve/release) |
| 8 | Divergent pagination | `page/size`, `limit/offset`, `cursor` |
| 9 | One explicit + one inferable-only business relationship | `x-api-galaxy-depends-on` vs alias-only link |

## 4. Verified demo path

See `samples/novacart/demo-script.md` and `docs/demo-guide.md`. 13 steps, 60–90 s.

## 5. Known limitations (kept honest in README)

Tracked in `README.md` → *Limitations*. Nothing optional is described as shipped.
