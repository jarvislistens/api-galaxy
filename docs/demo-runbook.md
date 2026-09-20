# Demo runbook

A presenter's script. Every number here was measured on the bundled NovaCart estate on
2026-09-19 — if the screen disagrees with the page, trust the screen and tell me.

See also `samples/novacart/demo-script.md`. `docs/demo-guide.md` is the shorter version. This is the one to rehearse from.

---

## Part 0 — Two minutes before you present

```bash
cd ~/Documents/api-galaxy
make demo
```

Wait for both lines, then open **http://127.0.0.1:3000**.

Checklist:

- [ ] Browser at **1440×900** or wider. Below ~1280 the inspector collapses into a drawer
      and the three-panel layout — which is half the point — disappears.
- [ ] Zoom at 100%. Cmd-0.
- [ ] **Close the Break Lab scenario picker** if a scenario from a previous run is
      selected. Start clean or step 7 makes no sense.
- [ ] If you plan to show the Arena: run it **once** beforehand to warm the model.
- [ ] Hide your bookmarks bar. The hero is full-viewport and it matters.

**Which estate to demo:** the bundled **NovaCart** one. It is seven services with nine
deliberate defects and it needs no model, no key and no internet. Do not import anything
live unless someone asks — see *Part 4*.

---

## Part 1 — The six-minute walkthrough

Timings are cumulative and assume you talk at a normal pace. The 90-second version is
steps 1, 5, 7, 8, 11.

### 1 · Landing — 0:00

**Do:** Land on `http://127.0.0.1:3000`. Do not scroll yet.

**Say:**
> "This is API Galaxy. The promise is on the screen: drop your API, watch it come alive,
> ask how it works, break it before production does.
> Everything you are about to see runs on this laptop. No model, no API key, no internet."

**Do:** Click **Explore the demo galaxy**.

---

### 2 · Overview — 0:25

**Do:** Let it land. Point at the counter row.

**Say:**
> "Seven services, thirty-two operations, a hundred and seventy-five fields. That is the
> whole estate, parsed deterministically — no model involved in any of it."

**Do:** Point at the two big numbers below.

**Say:**
> "Four hundred and ninety-nine relationships the documents *stated*. A hundred and
> eighty-five that something *inferred*. They are counted separately and drawn
> differently, everywhere, for the whole session. That separation is the product."

**Do:** Click **How was this derived?** → expand step 1 (**Parse**).

**Say:**
> "Four steps. Two read, two reason. It will tell you which is which at any point — and
> that is not a disclaimer, it is a filter you can toggle."

---

### 3 · Galaxy — 1:10

**Do:** Click **Galaxy** in the left nav. Wait for it to settle and fade in.

**Say:**
> "This is not a file tree. The estate is organised by business domain — Customer,
> Catalog, Cart, Order, Payment, Inventory, Shipping — which is not stated in any one
> specification. It is derived from what the services own."

**Do:** Click any **service node** (a rounded square). Inspector opens on the right.

**Say:**
> "Everything is clickable, and everything carries where it came from — the file and the
> exact JSON Pointer. Nothing here is unsourced."

**Do:** Point at the **Show inferred relationships** toggle in the left rail. Toggle it
off, then on.

**Say:**
> "Off: only what the documents say. On: the suggestions too, drawn dashed. You decide how
> much you trust."

---

### 4 · Journeys — 1:55

**Do:** Click **Journeys** → **Place Order** → **Play**.

**Say:**
> "A journey is a business flow told as real API calls. Six steps across five services.
> Watch the narration — that is written for someone who does not read YAML — and the
> technical detail underneath updates in step."

**Do:** Let two or three steps play. Do not wait for the end.

---

### 5 · Ask, no model — 2:40 ⭐

**Do:** Click **Ask**. **Point at the engine selector first** — it reads
*No model — graph only*.

**Say:**
> "Before I type anything: look at the engine. **No model.** This answer is going to be
> computed from the graph. It cannot invent anything, because there is nothing generating."

**Do:** Click the starter **How does checkout work?**

**Say (once it lands):**
> "Place Order, six steps, five services, named in call order. Thirteen nodes cited, each
> one clickable back to the specification. A chat assistant can also summarise a file —
> it cannot show you the path and it cannot prove it."

---

### 6 · Ask, the alias reveal — 3:20 ⭐⭐ **the moment**

**Do:** Click the starter **What depends on customer_id?**

**Say (slowly — pause after the first sentence):**
> "Used by seventeen operations across six services.
> *And it also appears as `cust_no` and `party_key`.*"

> "Three names. One person. Nothing in any of those three files says they are the same
> thing — the Order team called it `cust_no`, the Payment team called it `party_key`, and
> both are perfectly valid documents on their own.
> This is the failure you only find in production, and it is why file-by-file review
> does not catch it."

**Let that sit for a beat.** This is the single best thing the product does.

---

### 7 · Break Lab — 4:00

**Do:** **Break Lab** → **New scenario** → name it `Rename customer_id` → **Create**.

**Say:**
> "A scenario is a named clone. The imported specification is never touched — I can do
> anything here and nothing is damaged."

**Do:** Change kind → **Rename a field** → target `Customer.customer_id` → new name
`party_id` → **Apply change**.

**Say:**
> "So: a rename. The kind of change that gets approved in a five-minute code review."

---

### 8 · The blast radius — 4:40 ⭐

**Do:** Point at the four counters, left to right.

**Say:**
> "Two broken, four degraded, eighty-eight possibly affected, two hundred and
> seventy-two untouched.
> And underneath — **two of the six business journeys are broken: Register Customer and
> Place Order.** Not two schemas. Two things the business does."

**Do:** Point at a *possibly affected* row and read its reason aloud.

**Say:**
> "Note it grades itself. Something reached through a *suggested* alias never gets called
> broken — it says 'reached through a suggested relationship, so this is a possibility
> rather than a certainty'. It will not overstate what it knows."

---

### 9 · Repair — 5:20

**Do:** **Repair** tab → two repairs are offered. Point at both.

**Say:**
> "Two options. Map the old name to the new one at the boundary so existing consumers
> keep working — or revert. It has a migration checklist for each."

**Do:** Apply **Revert the rename of 'customer_id'**.

**Say:**
> "And the journeys re-validate. It only says restored *after* validation passes —
> that word is earned, not printed."

---

### 10 · Model Arena — 5:50 *(optional; see Part 3)*

**Do:** **Model Arena** → Provider A `Deterministic`, Provider B `Ollama`,
**Scope: Customer** (never the whole estate) → **Run arena**.

**Say while it runs (~90 s — fill the time, do not stare):**
> "Same context, same schema, same prompt version, both sides. That is the only way a
> comparison means anything — and it was not true until last week; the deterministic side
> was quietly reading the whole estate while the model saw one domain."

**Say (on results):**
> "Instant versus ninety seconds. Five entities versus one — but the model proposed four
> alias candidates the rules did not.
> And the column I actually care about: **hallucinated references, zero on both sides.**
> This is not about picking a winner. It is about measuring whether a model invents
> things on *your* data before you trust it with them."

---

### 11 · Export — 6:20

**Do:** **Reports** → **Interactive report** → download → **open the file from Finder**.

**Say:**
> "One self-contained file. No backend, no API key, no internet — it works on a plane.
> Search, pan, zoom, click a node for its provenance, play a journey.
> The app is a workbench. *This* is the deliverable."

---

## Part 2 — Numbers cheat-sheet

Measured 2026-09-19 on the bundled estate.

| Where | Number |
| --- | --- |
| Overview | 7 services · 32 operations · 30 schemas · 175 fields |
| Overview | 7 domains · 6 journeys · **15 findings** |
| Overview | 366 nodes · 684 relationships |
| Overview | **499 observed / 185 inferred** |
| Ask, checkout | Place Order · 6 steps · 5 services · 13 nodes cited |
| Ask, customer_id | 17 operations · 6 services · aliases `cust_no`, `party_key` |
| Break Lab | **broken 2 · degraded 4 · possibly affected 88 · unaffected 272** |
| Break Lab | **2 of 6 journeys broken** — Register Customer, Place Order |
| Arena (Customer domain) | deterministic 0 ms · ollama ~90 s · hallucinated 0 / 0 |

---

## Part 3 — The Model Arena: read this before including it

It works, but it is the riskiest ninety seconds in the demo.

- **Always scope to one domain.** The whole estate takes minutes.
- **It is not cancellable** once started.
- **Run it once before you present** so the model is warm.
- `qwen3:4b` is the tested default. `qwen2.5:7b-instruct` is *not* better here — measured
  slower output quality and one invented reference.
- If you are short on time, **cut it**. Steps 6 and 8 are the demo; the Arena is a
  capability you can describe in one sentence instead.

---

## Part 4 — Questions you will get

**"Does it work on my API, or only this sample?"**
> Open a second tab on `/import` and drag in `samples/try-it/booking-api.yaml` *and*
> `billing-api.yaml` together. Thirteen findings in about two seconds. Say: "Two files,
> eight problems, and three of them only exist *between* the two — import them separately
> and those three vanish."

**"Is it reading my source code?"**
> No. It reads specification documents only. It never opens a `.py` or a `.ts`.

**"What if my specs are out of date?"**
> Then the graph is out of date. It believes the documents. It will not find a bug in your
> implementation — only in your contracts. Say this plainly; it buys credibility.

**"Is the AI making this up?"**
> Show them the engine selector on Ask set to *No model*. The default path has no model at
> all. When a model is used, everything it proposes is dashed, labelled, and discardable.

**"Can it see undocumented consumers?"**
> No — so the real blast radius may be *wider* than what you just saw, never narrower.

**"Where does my data go?"**
> Settings → Privacy, top of the page. External providers are one switch, off by default
> in spirit, and every external call shows you the exact sanitised payload first.

---

## Part 5 — Things that will trip you up

- **`/workspace/<id>/overview` is a 404.** Overview is the index route. Use the nav.
- **Kimi shows "not ready".** That is correct and it is the privacy story — do not
  apologise for it.
- **The "N" circle bottom-left** is the Next.js dev badge. It is not in a production build.
- **Do not leave a stale scenario selected** in Break Lab before you start.
- **Do not resize the window mid-demo** — it is handled, but the graph re-fits and you
  will lose your place.
