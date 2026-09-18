"""Versioned prompt templates and the JSON Schemas their responses must satisfy.

``PROMPT_TEMPLATE_VERSION`` is part of every cache key and every decision-log entry, so
changing a template here invalidates cached model output and is visible in the audit trail.

The prompts share one shape: a hard instruction block, the bounded graph context, the
exact schema, and an explicit whitelist of IDs. They all say the same three things to the
model — only use these IDs, do not invent endpoints or fields, return JSON only — because
that is what actually keeps small local models in line.
"""

from __future__ import annotations

import json
from typing import Any

from api_galaxy import PROMPT_TEMPLATE_VERSION
from api_galaxy.contracts.providers import GraphContext

__all__ = [
    "ANSWER_SCHEMA",
    "ENRICHMENT_SCHEMA",
    "PROMPT_TEMPLATE_VERSION",
    "REPAIR_SCHEMA",
    "answer_prompt",
    "enrichment_prompt",
    "repair_prompt",
]

GROUND_RULES = """\
You are a careful API analyst. You are looking at facts that were already extracted from
OpenAPI documents by a deterministic parser. Your job is ONLY to add business meaning.

Hard rules:
- Never invent an endpoint, schema, field, service or dependency. If it is not in the
  context below, it does not exist.
- Only ever cite IDs from the ALLOWED IDS list. Any other ID will be discarded.
- Do not contradict the parsed facts. If the context says an operation is deprecated, it is.
- Express uncertainty with the confidence number, not with hedging prose.
- Reply with ONE JSON object and nothing else. No prose, no markdown, no code fence.
"""


def _context_block(context: GraphContext, *, max_operations: int = 60,
                   max_schemas: int = 40) -> str:
    lines: list[str] = [f"PROJECT: {context.project_name}", f"SCOPE: {context.chunk_label}", ""]

    if context.services:
        lines.append("SERVICES:")
        for service in context.services:
            lines.append(
                f"- {service.get('id')} | {service.get('name')} | {service.get('description', '')[:160]}"
            )
        lines.append("")

    if context.operations:
        lines.append("OPERATIONS:")
        for op in context.operations[:max_operations]:
            flags = []
            if op.deprecated:
                flags.append("DEPRECATED")
            if not op.secured:
                flags.append("NO-AUTH")
            summary = (op.summary or op.description or "")[:160]
            lines.append(
                f"- {op.id} | {op.method.upper()} {op.path} | {op.service} | {summary}"
                + (f" | {' '.join(flags)}" if flags else "")
            )
        if len(context.operations) > max_operations:
            lines.append(f"  … and {len(context.operations) - max_operations} more")
        lines.append("")

    if context.schemas:
        lines.append("SCHEMAS:")
        for schema in context.schemas[:max_schemas]:
            fields = ", ".join(
                f"{f.get('name')}:{f.get('type', '?')}" for f in schema.fields[:12]
            )
            lines.append(
                f"- {schema.id} | {schema.name} | {schema.service} | "
                f"{schema.description[:120]} | fields: {fields}"
            )
        if len(context.schemas) > max_schemas:
            lines.append(f"  … and {len(context.schemas) - max_schemas} more")
        lines.append("")

    if context.existing_domains:
        lines.append("DOMAINS ALREADY IDENTIFIED: " + ", ".join(context.existing_domains))
        lines.append("")

    lines.append("ALLOWED IDS (cite only these):")
    lines.append(", ".join(context.allowed_node_ids[:400]))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Enrichment
# --------------------------------------------------------------------------------------

_CONFIDENCE = {"type": "number", "minimum": 0, "maximum": 1}

ENRICHMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["entities", "domains", "journeys", "aliases", "relations"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "represented_by": {"type": "array", "items": {"type": "string"}},
                    "confidence": _CONFIDENCE,
                },
            },
        },
        "domains": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "service_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": _CONFIDENCE,
                },
            },
        },
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "operation_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": _CONFIDENCE,
                },
            },
        },
        "journeys": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "operation_ids"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "operation_ids": {"type": "array", "items": {"type": "string"}},
                    "narrations": {"type": "array", "items": {"type": "string"}},
                    "confidence": _CONFIDENCE,
                },
            },
        },
        "aliases": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["canonical_name", "member_ids"],
                "properties": {
                    "canonical_name": {"type": "string"},
                    "member_ids": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                    "confidence": _CONFIDENCE,
                },
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source_id", "target_id"],
                "properties": {
                    "source_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "relation": {"type": "string"},
                    "rationale": {"type": "string"},
                    "confidence": _CONFIDENCE,
                },
            },
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string"},
                    "node_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": _CONFIDENCE,
                },
            },
        },
        "rationale": {"type": "string"},
    },
}


def enrichment_prompt(context: GraphContext, *, max_items: int = 24) -> str:
    return f"""{GROUND_RULES}
TASK: Read the API estate below and describe what it does in business terms.

Produce, at most {max_items} of each:
- entities: the business things this estate manages (Customer, Order, Shipment…).
  `represented_by` must list the schema or field IDs that carry the entity.
- domains: business areas, each owning one or more services.
- capabilities: what the estate can DO, phrased as a business verb phrase.
- journeys: end-to-end flows. `operation_ids` must be IN CALL ORDER. Add one narration
  sentence per operation, written for a non-technical reader.
- aliases: groups of differently-named fields that mean the same thing. This is the most
  valuable output — look for identifiers that changed name across a service boundary.
- relations: dependencies the specification does NOT declare but that the descriptions
  imply. Only include one if you can say why in `rationale`.
- risks: business or governance concerns you can see in the descriptions.

{_context_block(context)}

Return JSON matching exactly this schema:
{json.dumps(ENRICHMENT_SCHEMA, indent=None)}
"""


# --------------------------------------------------------------------------------------
# Question answering
# --------------------------------------------------------------------------------------

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["answer", "highlighted_node_ids"],
    "properties": {
        "answer": {"type": "string"},
        "technical_explanation": {"type": "string"},
        "highlighted_node_ids": {"type": "array", "items": {"type": "string"}},
        "path": {"type": "array", "items": {"type": "string"}},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {"type": "string"},
                    "why": {"type": "string"},
                },
            },
        },
        "inference_note": {"type": "string"},
        "confidence": _CONFIDENCE,
    },
}


def answer_prompt(context: GraphContext, question: str) -> str:
    return f"""{GROUND_RULES}
TASK: Answer the user's question about this API estate using ONLY the context below.

QUESTION: {question}

Requirements:
- `answer`: two to four sentences, plain language, no jargon, no hedging.
- `highlighted_node_ids`: every ID the answer depends on, so the graph can light them up.
- `path`: if the answer is a flow, the IDs in order.
- `evidence`: for each cited ID, one clause saying what it contributes.
- `inference_note`: if any part of your answer is inference rather than something the
  specification states, say which part. Leave empty if everything is a stated fact.
- If the context does not contain the answer, say so plainly in `answer` and return an
  empty `highlighted_node_ids`. Do not guess.

{_context_block(context)}

Return JSON matching exactly this schema:
{json.dumps(ANSWER_SCHEMA, indent=None)}
"""


# --------------------------------------------------------------------------------------
# Repairs
# --------------------------------------------------------------------------------------

REPAIR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["repairs"],
    "properties": {
        "repairs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "rationale"],
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "kind": {"type": "string"},
                    "target_ids": {"type": "array", "items": {"type": "string"}},
                    "migration_steps": {"type": "array", "items": {"type": "string"}},
                    "confidence": _CONFIDENCE,
                },
            },
        }
    },
}

ALLOWED_REPAIR_KINDS = (
    "add_alias_mapping",
    "restore_field_name",
    "restore_type",
    "restore_field",
    "restore_endpoint",
    "restore_response",
    "restore_service",
    "semantic_mapping",
    "version_endpoint",
    "tolerant_reader",
)


def repair_prompt(context: GraphContext, changes: list[str], broken: list[str],
                  broken_journeys: list[str]) -> str:
    return f"""{GROUND_RULES}
TASK: Propose ways to repair the breakage caused by a simulated change.

WHAT CHANGED:
{chr(10).join(f'- {c}' for c in changes) or '- (nothing recorded)'}

WHAT BROKE:
{chr(10).join(f'- {b}' for b in broken[:30]) or '- (nothing recorded)'}

BROKEN JOURNEYS:
{chr(10).join(f'- {j}' for j in broken_journeys) or '- (none)'}

Requirements:
- Prefer repairs that keep existing consumers working over repairs that ask them to change.
- `kind` must be one of: {', '.join(ALLOWED_REPAIR_KINDS)}.
- `migration_steps` should be an ordered, concrete checklist an engineer can follow.
- Never propose running code, a query, or a script. Describe the specification change only.

{_context_block(context)}

Return JSON matching exactly this schema:
{json.dumps(REPAIR_SCHEMA, indent=None)}
"""
