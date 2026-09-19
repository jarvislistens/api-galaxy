# ADR 003 — Provenance on everything, and the fact/inference boundary

**Status:** accepted · 2026-09-19

## Context

The thing that makes API Galaxy different from an assistant summarising a spec file is
that you can always ask *how do you know that?* and get a file and a JSON Pointer back.
That only holds if it is impossible to add something to the graph without saying where it
came from.

It is also the thing that is easiest to lose. One convenience helper that defaults
provenance to "unknown", and six months later half the graph is unattributable.

## Decision

`Provenance` is a **required field** on `GraphNode`, `GraphEdge` and `Risk`. There is no
default and no constructor that omits it. It carries:

```
source_kind              specification | deterministic_rule | bundled_analysis
                         | ai_inference | user_edit | scenario
explanation              one sentence, plain language, no jargon
source_file              the document it came from
source_pointer           RFC 6901 pointer into that document
rule_id                  which rule, when a rule produced it
confidence               0..1, when the thing is a judgement
provider / model         which model, when a model produced it
prompt_template_version  so a cached result can be invalidated
created_at / updated_at
```

Alongside it, `acceptance` records the human decision: `observed`, `proposed`,
`accepted`, `rejected`, `superseded`.

## The rule that took three attempts to get right

Facts and inferences live in the same graph but are **never merged**, and the boundary is
drawn by `source_kind` *and* `acceptance` together — not by either alone.

The first version keyed only on `source_kind`. That put alias detection on the wrong side:
it is a `deterministic_rule`, so `source_kind.is_fact` was true and it rendered solid,
which reads as "the specification says these three fields are the same thing". It does
not. Alias detection only ever *proposes*.

The fix was then re-derived, separately and slightly differently, in three places — the
stroke, the graph filter, and the impact scorer. Two of them were corrected; the third was
missed, and an aliased field in another service kept being reported as a **broken
contract**. Same bug, third instance, because the rule lived in three heads.

So it now lives in exactly one: **`Standing`**.

```
standing_of(source_kind, acceptance) →
    REJECTED    a person ruled it out
    ACCEPTED    a person asserted or confirmed it          → dotted
    SUGGESTED   a rule or a model proposes it              → dashed
    STATED      a document says so, nobody has qualified it → solid
```

`GraphNode.standing`, `GraphEdge.standing`, `stroke`, `is_fact`, the graph filter, the
stats counters and the impact scorer are all derived from it. There is no second
definition to drift.

## Standing decides how far a change can travel

The impact scorer combines standing with the **edge type** — the other half of the
ontology — so that distance alone can no longer overstate a claim:

| the route includes | strongest possible verdict |
| --- | --- |
| only `STATED` hops along contract edges | **broken** |
| an `ACCEPTED` hop, or a semantic edge (`ALIAS_OF`, `REPRESENTS`) | **degraded** |
| a `SUGGESTED` hop | **potentially affected** |

This is what makes the stated assumption *"a suggested relationship never produces
broken"* true by construction rather than by assertion. `DependencyPath` carries the hops
so the caller can see them, and the UI shows the route as
`customer_id —alias of→ cust_no` rather than two bare names.

## Consequences

* **Accepting an inference does not make it a fact.** It records that a person agreed. The
  provenance becomes `user_edit`, the stroke becomes dotted, and the decision goes to the
  append-only log with the provider, model and prompt template version that produced it.
* **Nothing auto-merges.** An alias cluster is never applied on the user's behalf, however
  confident it is.
* **Meaning is never carried by colour alone.** Every state has a stroke pattern, an icon
  and a word. Roughly one man in twelve cannot read a red/green distinction, and a printed
  report has no colour at all.
* Counts are reported separately — *observed relationships* and *inferred relationships*
  are two numbers on the Overview, never one total.
* Because provenance is mandatory, a new rule or a new provider cannot quietly add
  unattributable edges. A test walks the whole graph and asserts every node and edge has a
  non-empty explanation.
