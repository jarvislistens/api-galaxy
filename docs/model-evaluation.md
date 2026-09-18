# Evaluating models on your own estate

API Galaxy ships a Model Arena because "which model should I use for this?" is an
empirical question, and the only estate whose answer matters is yours.

This document explains what the Arena measures, why those things, and how to read a run
without fooling yourself.

## What makes the comparison fair

Every provider in a run gets:

* the **same sanitized context** — the same bounded slice of the graph, chunked the same
  way, with the same explicit list of node IDs it may cite;
* the **same prompt template**, at the same version;
* the **same JSON Schema** for its response;
* the **same parser**, so the outputs are normalised identically before anything is scored.

If any of those differed, the comparison would be measuring the harness rather than the
model. The prompt template version is recorded on the run and in every decision-log entry
for exactly that reason.

## The metrics, and why each one is there

| Metric | What it tells you |
| --- | --- |
| **Valid structured output** | Whether it follows instructions at all. A model that cannot reliably return the schema costs you a retry loop on every call. |
| **Retries** | How close it was to failing. Zero retries and two retries are very different experiences at scale. |
| **Hallucinated references** | IDs it invented that do not exist. **The most important number here.** |
| **Entities / domains / capabilities / journeys / aliases / relations** | Recall of the semantic layer — how much it actually found. |
| **Latency** | Wall-clock. A local 4B model is often faster end-to-end than a remote frontier model once the network is included. |
| **Input / output tokens** | What you are paying for, when you are paying. |
| **Estimated cost** | Tokens × your editable pricing. An estimate, never a bill. |

### Why hallucinated references is the headline

Every other metric rewards saying more. That one is the counterweight.

A model that invents plausible-sounding IDs will score well on entity and relation counts
while being actively dangerous, because a confident wrong dependency is worse than a
missing one. API Galaxy discards invented references before they can reach the graph — but
it *counts* them, and the count is the honesty signal. A model with high recall and a
non-zero hallucination count has not earned the recall.

## Agreement, disagreement, conflict

Relationships from the two providers are bucketed:

* **Consensus** — both proposed it. The strongest signal available without a human.
* **Only A / only B** — one saw something the other did not. Could be better recall, could
  be noise. Read the rationale.
* **Conflict** — both linked the same pair but disagree about *how*. These are the rows
  worth your attention: two models reading the same prose and reaching different
  conclusions usually means the prose is ambiguous, which is itself a finding.

Alias and domain agreement are reported as Jaccard overlap, because those are set
comparisons rather than pairwise ones.

## Reading a run honestly

**Consensus is not truth.** Two models trained on overlapping data agreeing is weaker
evidence than it looks. Consensus on something *neither* could have read directly from the
specification is interesting; consensus on something restated in the description is not.

**A single run is an anecdote.** Temperature is 0.1, not 0, and context chunking varies
with the estate. Run a few times before concluding anything about a model.

**Scope matters.** Comparing on one domain measures depth. Comparing on the whole estate
measures breadth *and* how gracefully a model handles a context that is too big. They are
different questions and can have different winners.

**The deterministic provider is a real participant.** Compare against it deliberately. If a
model is not beating graph traversal on a question, use graph traversal — it is instant,
free, reproducible and cannot hallucinate.

## You decide, and the decision is recorded

Nothing from a run enters the graph on its own. Each row has **Accept A / Accept B / Merge /
Reject both**, and whatever you choose is written to an append-only decision log with the
provider, model, prompt template version, timestamp, your action and the supporting source
references.

That log is the point. Six months later, "why does the graph say these two fields are the
same?" has an answer: who decided, when, based on which model output, under which prompt.

## Pricing

Shipped pricing values are **examples**, labelled as examples, and stamped with
`updated_by: app`. Edit them in Settings → Pricing; your edit is stamped with
`updated_by: local-user` and the time. Local providers are zero by construction — you pay
in electricity, not tokens.

Nothing in the product treats a price as permanent truth, because provider pricing changes
more often than this application will.

## Reproducing a result

A cached result is keyed on all six of: specification fingerprint, context fingerprint,
provider, model string, prompt template version, task type. Change any one and it is a
different question, and it is recomputed.

To re-run a comparison honestly after changing a prompt, bump `PROMPT_TEMPLATE_VERSION` in
`apps/api/api_galaxy/__init__.py`. Old cached results become unreachable and old decision
log entries remain labelled with the version that produced them.
