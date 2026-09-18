# `@api-galaxy/contracts`

JSON Schemas for every shape that crosses a boundary in API Galaxy.

The **source of truth** is the Pydantic models in `apps/api/api_galaxy/contracts/`.
Everything in `schemas/` is generated from them:

```bash
python scripts/export_contracts.py           # regenerate
python scripts/export_contracts.py --check   # fail if stale (CI)
```

## Why generated schemas rather than generated TypeScript

The web app's types in `apps/web/src/lib/types.ts` are **hand-written**. That is a
deliberate choice: the surface is small and stable, and a code generator would be one more
process that has to be running for the app to build, plus a large volume of machine-written
types that nobody reads.

What we do want is something authoritative to check against. These schemas give us that:
they are the contract, they are versioned with the app, and an external consumer of a
JSON-LD or CSV export can validate against them without reading Python.

If the hand-written types and these schemas ever disagree, the schemas are right.
