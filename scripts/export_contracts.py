#!/usr/bin/env python
"""Write the JSON Schemas both sides of the app are checked against.

The Pydantic models in `apps/api/api_galaxy/contracts` are the source of truth. This
script projects them into `packages/contracts/` so the web app's hand-written TypeScript
types can be diffed against something authoritative, and so an external consumer of an
export has a schema to validate against.

    python scripts/export_contracts.py            # write
    python scripts/export_contracts.py --check    # fail if out of date (for CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

OUTPUT_DIR = REPO_ROOT / "packages" / "contracts" / "schemas"


def collect() -> dict[str, dict]:
    from api_galaxy import __version__
    from api_galaxy.contracts.analysis import EstateOverview, Journey, Risk
    from api_galaxy.contracts.graph import GraphEdge, GraphNode, KnowledgeGraph, Provenance
    from api_galaxy.contracts.providers import (
        ArenaComparison,
        DecisionRecord,
        EnrichmentResult,
        GraphAnswer,
        ProviderHealth,
    )
    from api_galaxy.contracts.scenario import ImpactReport, Repair, Scenario

    models = [
        Provenance, GraphNode, GraphEdge, KnowledgeGraph,
        Risk, Journey, EstateOverview,
        Scenario, ImpactReport, Repair,
        ProviderHealth, EnrichmentResult, GraphAnswer, ArenaComparison, DecisionRecord,
    ]
    schemas = {model.__name__: model.model_json_schema() for model in models}
    schemas["_index"] = {
        "app_version": __version__,
        "generated_by": "scripts/export_contracts.py",
        "models": sorted(m.__name__ for m in models),
        "note": "Generated from the Pydantic contracts. Do not edit by hand.",
    }
    return schemas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Exit non-zero if the written schemas differ from the models.")
    args = parser.parse_args()

    schemas = collect()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []

    for name, schema in schemas.items():
        path = OUTPUT_DIR / f"{name}.schema.json"
        rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != rendered:
                stale.append(path.name)
        else:
            path.write_text(rendered, encoding="utf-8")

    if args.check:
        if stale:
            print("Out of date: " + ", ".join(stale))
            print("Run: python scripts/export_contracts.py")
            return 1
        print(f"{len(schemas)} schema(s) up to date.")
        return 0

    print(f"Wrote {len(schemas)} schema(s) to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
