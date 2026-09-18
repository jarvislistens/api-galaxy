# ADR 005 — Storage layout, and where the design system lives

**Status:** accepted · 2026-09-19

Two smaller decisions that would otherwise be invisible.

## Storage: SQLite for records, files for documents

A graph is read whole and written whole. Shredding 366 nodes into rows to reassemble them
on every request would buy nothing — there is no query we want to run *inside* a graph
that NetworkX does not answer better in memory.

So:

* **SQLite** holds the things we actually query: projects, scenarios, jobs, settings,
  exports, and the decision log.
* **The filesystem** holds documents: `graph.json`, `estate.json`, `risks.json`,
  `journeys.json`, `aliases.json`, `meta.json` per project, under the app data directory.

The in-memory project registry is a cache, never the source of truth. A restart rehydrates
every project from disk, and nothing exists only in RAM.

`NetworkXGraphRepository` sits behind a `GraphRepository` protocol so Kùzu or Neo4j can
replace it later without touching callers. We did not start there: an embedded graph
database is a dependency, a migration story and a second query language, and at estate
scale the algorithms run in milliseconds in NetworkX.

### The decision log is append-only by construction

`DecisionRecordRow` has no update path anywhere in the codebase — not a policy, an absence
of code. `record_decision` inserts; nothing else touches it.

### Secrets

External API keys go to the OS keychain when `keyring` is installed, and otherwise live in
process memory for the session only. They are never written to SQLite, never written to a
file, and never logged. The Settings screen says which of the two is happening rather than
implying the stronger one.

## The design system lives inside `apps/web`

The recommended shape had a `packages/design-system`. We put it in
`apps/web/src/components/ui/` instead.

**Why:** exactly one consumer. A separate package would add a build step, a second
`tsconfig`, a watch process in development and roughly a hundred megabytes of duplicated
tooling — to solve a sharing problem that does not exist. If a second consumer ever
appears, extracting it is a directory move.

`packages/report-runtime` **is** a separate package, because it genuinely has a different
consumer and different constraints: it is inlined into exported HTML files, so it must be
plain ES2018 with no build step, no framework and no imports.

`packages/contracts` holds the JSON Schemas both sides are checked against. The TypeScript
types in `apps/web/src/lib/types.ts` are hand-written rather than generated — the surface
is small and stable, and a generator would be one more thing that has to be running for
the app to build.
