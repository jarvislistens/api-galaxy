# ADR 002 — The provider abstraction, and why deterministic comes first

**Status:** accepted · 2026-09-19

## Context

API Galaxy uses a language model for semantic interpretation: business entities,
capabilities, journeys, aliases, plain-language explanations, repair suggestions. It must
also be **fully useful with no model at all** — the bundled demo has to be impressive on a
laptop with nothing installed, and an air-gapped reviewer has to get real value.

Those two requirements pull in opposite directions unless the model is behind a seam.

## Decision

One protocol, `SemanticProvider`, with four methods — `health`, `enrich`, `answer`,
`propose_repairs` — and three implementations:

| Provider | Role | Needs |
| --- | --- | --- |
| `DeterministicProvider` | Computes semantics from the graph in code. Always available, instant, reproducible. | nothing |
| `OllamaProvider` | The default when a model is wanted. Local, private. | Ollama running |
| `KimiProvider` | Optional external analysis. | a key **and** per-project consent |

`ComparisonService` runs the same task on two of them and normalises the metrics — that is
the Model Arena.

## Why a deterministic provider at all

It would have been easier to make "no model" mean "no answers". We did not, because:

* **The demo has to work in the first ten seconds.** Asking someone to install Ollama and
  pull a 2.5 GB model before they see anything is how a tool goes unevaluated.
* **It is the floor for the Arena.** "Better than nothing" is only measurable if nothing
  is a real, scored participant.
* **Facts should not need a model.** "What depends on `customer_id`?" is graph traversal.
  Answering it with an LLM would be slower, less reliable and less explainable.

The deterministic provider classifies the question by intent, then answers from the graph:
journeys for flow questions, transitive dependents for impact questions, alias clusters for
ambiguity questions, the risk list for safety questions, and lexical retrieval otherwise.
It handles every starter question in the product.

## Three invariants every provider inherits

Enforced in `providers/base.py` so no adapter can forget them:

1. **Strict JSON, validated.** Each task declares a versioned schema. The response is
   parsed and validated; on failure we retry at most twice, feeding the validation error
   back. After that we return an empty result rather than a guess.
2. **ID whitelisting.** A model may only reference node IDs that were in the context it
   was given. Everything else is dropped and counted as a hallucinated reference — which
   the Arena then scores, and the Ask panel discloses.
3. **No hidden reasoning, no executable output.** We strip think-style tags and store a
   short rationale only. We never accept Cypher, SQL, shell, JavaScript or Python from a
   model for execution.

## Consequences

* Adding a provider is one class and one registry entry.
* Any provider can be unavailable at any time; `health()` returns an actionable
  `setup_hint` rather than an exception, and the UI greys the option out with the reason.
* The prompt template version is part of the cache key *and* of every decision-log entry,
  so changing a prompt invalidates cached output and is visible in the audit trail.
* `qwen3:4b` is the default model because of a measured detail: with thinking enabled,
  Ollama returns the content in a separate `thinking` field and leaves `response` empty,
  so the caller silently sees nothing. `OllamaProvider` sends `think: false` and, belt and
  braces, falls back to reading `thinking` if `response` comes back empty.
