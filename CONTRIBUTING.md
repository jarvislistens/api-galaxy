# Contributing

Thanks for looking. This is a Sunday Builds project, so the bar is "would I want to
maintain this?" rather than "does it pass CI".

## Getting set up

```bash
make setup      # Python venv + node modules
make check      # lint, types, tests — should be green before you start
make demo       # both servers plus the NovaCart estate
```

Prerequisites: Python 3.11–3.13, Node 20+. Ollama is optional — everything works without it.

## The rules that are not negotiable

These are the product, not style preferences. A change that breaks one of them will not be
merged however useful it is otherwise.

1. **Deterministic before generative.** If a fact can be computed from the specification,
   compute it. Language models are for interpretation, never for facts.
2. **Provenance on everything.** There is no way to add a node or an edge without saying
   where it came from, and there should not be one. If you find yourself wanting a
   `Provenance` default, that is the smell.
3. **Facts and inferences never merge.** `source_kind` plus `acceptance` decides whether
   something renders solid, dashed or dotted. Changing that logic means changing
   `GraphEdge.stroke`, and the graph filter and every export follow automatically — keep
   it that way rather than duplicating the rule.
4. **Nothing leaves the machine silently.** Any new external call goes through
   `providers/sanitizer.py` and requires per-project consent. No exceptions, including for
   "just metadata".
5. **Never claim something works that does not.** If an optional dependency is missing,
   the feature reports itself unavailable with the reason. It does not silently substitute
   something else, and the UI does not show a dead button.
6. **Meaning is never carried by colour alone.** Every state needs a stroke pattern, an
   icon or a word as well.

## Code style

**Python.** `from __future__ import annotations`, full type hints, `ruff` clean. Module
docstrings explain *why the module exists and what rule it enforces* — not what the
functions are called, which the reader can see. Inline comments only where a reader would
otherwise be puzzled: a non-obvious ordering, a workaround, a rejected alternative.

**TypeScript.** Strict mode, no `any` in new code unless a third-party type forces it (and
then with a comment saying so). Components are `"use client"` only when they need to be.

**Both.** Match the file you are editing. Comment density, naming and idiom should be
indistinguishable from the surrounding code.

Good comment:

```python
# Card before phone, deliberately. A 16-digit card number also satisfies the phone
# pattern, and whichever rule runs first consumes it — so the more sensitive
# classification has to go first.
```

Bad comment:

```python
# Loop over the rules
for rule in rules:
```

## Tests

Every change to analysis, providers or exports needs a test. Tests assert **behaviour a
user would notice**, not implementation details.

```bash
make test-api                    # pytest
.venv/bin/python -m pytest tests/unit/test_analysis.py -q -k alias
make test-web                    # tsc + eslint
make e2e                         # Playwright (needs both servers up)
```

If you add a rule, add a case to the NovaCart sample that triggers it and a test that
asserts it fires — and, just as importantly, a case where it should *not* fire. Most of
the bugs found while building this were rules firing too eagerly, not too rarely.

## Adding things

**A risk rule:** write it in `analysis/rules.py`, add it to `ALL_RULES` and
`RULE_CATALOG`, and mark `heuristic=True` if it makes a judgement. Heuristic rules are
labelled as such everywhere they surface, which is what makes them acceptable.

**A provider:** implement the four `SemanticProvider` methods, register it in
`app/state.py`. The base class already enforces schema validation, bounded retries and ID
whitelisting — do not bypass them.

**An export format:** one renderer function taking a `ReportBundle`, plus one
`EXPORT_FORMATS` entry. The disclosure block comes for free. If it needs an optional
dependency, probe it at import and set `available`/`unavailable_reason`.

**A change kind for Break Lab:** add to `ChangeKind` and `CHANGE_LABELS`, handle it in
`_apply_one`, and give it a deterministic repair in `propose_deterministic_repairs`. A
change you cannot repair is half a feature.

## Commits and pull requests

Present tense, explain *why*: `fix: alias detection over-merged identifiers across
services`. Say what you verified, and say what you did not. "I could not test the Kimi
path because I have no key" is a useful sentence.

## Reporting a bug

Include: what you imported (a minimal spec if you can share one), what you expected, what
happened, and the correlation ID from the error if there was one — it appears in both the
UI and the server log.

Security issues go to `SECURITY.md` instead, not to the issue tracker.
