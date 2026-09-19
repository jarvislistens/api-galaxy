# Demo guide

The verified 13-step demo, what each step is actually proving, and how to recover when
something goes sideways in front of an audience.

The narrated script with timings lives in
[`samples/novacart/demo-script.md`](../samples/novacart/demo-script.md). This document is
the presenter's notes behind it.

## Before you start

```bash
# starts both servers and loads NovaCart
make demo
```

Open `http://127.0.0.1:3000`. Nothing else is required — no model, no key, no network.

A 60-second sanity check:

- [ ] The landing page loads and the galaxy is drifting.
- [ ] **Explore the demo galaxy** reaches the workspace in under two seconds.
- [ ] The Overview shows 7 domains and 6 journeys.
- [ ] Ask → "How does checkout work?" returns *Place Order* with a lit path.
- [ ] Reports → the format grid shows what is available on this machine.

If you intend to show Ollama, also run `ollama list` and confirm your model is there.
If you do not, say so out loud once — "this is running with no model at all" is a stronger
line than most people expect.

## The thirteen steps, and what each one proves

| # | Step | The point |
| --- | --- | --- |
| 1 | Land, click **Explore the demo galaxy** | Zero setup. No account, no key, no wait. |
| 2 | Watch it organise into seven domains | Seven *files* became seven *business areas*. It did not ask you to understand OpenAPI. |
| 3 | Read the counts: observed vs inferred | Two numbers, never one. The product knows which of its own claims are facts. |
| 4 | Open **Place Order** and play it | A business flow, narrated, with the technical detail alongside — not instead. |
| 5 | Ask "How does checkout work?" | Plain English in, graph out. |
| 6 | Watch the evidence path light up | Every hop cites a file and a JSON Pointer. This is the line between this and a chatbot. |
| 7 | Break Lab: rename `customer_id` → `party_id` | The base project is untouched; a scenario is a clone. |
| 8 | Read the shockwave and the broken journeys | Broken / degraded / possibly affected, each with the dependency chain that explains it. |
| 9 | Apply the alias-mapping repair | A repair that keeps existing consumers working, not one that reverts your change. |
| 10 | Replay checkout | "Journey restored" appears **only** because validation passed. |
| 11 | Model Arena | Same context, same schema, side by side — including invented references. |
| 12 | Export the journey as SVG and Mermaid | Scoped exports, not just whole-project dumps. |
| 13 | Export the PDF and the interactive HTML report | The HTML opens from a file with no backend. That usually gets the room. |

## The three moments that land

**Step 6 — the citation.** Most people have seen an assistant describe an API. Almost
nobody has seen one point at the exact line it read. Slow down here and click one piece of
evidence.

**Step 8 — the blast radius.** Renaming one field breaks two journeys across five
services. This is the moment the audience recognises their own estate.

**Step 13 — the HTML report.** Open it in a new tab from the downloaded file and use it:
search, click a node, play a journey. "This works on a laptop with no internet and no
install" is the strongest single claim in the demo.

## If something goes wrong

**The workspace will not load.** The backend is not running. `curl
http://127.0.0.1:8099/api/v1/health`. Recover by talking through the Overview screenshot
in the README while you restart it.

**Ask returns a lexical-match answer instead of a journey.** You asked something outside
the five starters. Use a starter chip — they are there for exactly this.

**A model is slow on stage.** Switch the provider to **No model — graph only**. Every
starter question still works, instantly. This is a feature, not a fallback: say so.

**PDF or PNG is greyed out.** Those need system libraries. Point at the reason shown next
to the format — an honest "this installation cannot do that, and here is why" is a better
look than a spinner that never resolves. Export HTML or Markdown instead.

**An export downloads but will not open.** Check the size in the history table. Zero bytes
means the render failed; the correlation ID is in the error toast and in the server log.

## Running it with a model

Everything above works with no model. To show the AI layer:

```bash
ollama pull qwen3:4b
```

Then in Settings confirm Ollama is **Ready**, and switch the Ask provider to **Local &
Private**. Two things worth narrating:

- the answer is now free-form rather than template-driven, *and* still restricted to node
  IDs that exist — if the model invents one you will see it reported as discarded;
- it is still local. The provider indicator in the top bar says so throughout.

For the Arena you need two providers. `deterministic` + `ollama` is a perfectly good
comparison and needs no key.

## Timing

90 seconds narrated at a comfortable pace. The 60-second cut drops steps 11 and 12 —
Model Arena and the scoped diagram exports — which are the two that need the most
explanation and land least without context.

Do not rush steps 6, 8 and 10. Everything else is scaffolding for those three.
