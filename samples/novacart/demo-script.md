# NovaCart demo script — 60 to 90 seconds

**Estate:** NovaCart (fictional, bundled). **Target runtime:** 85 seconds.
**Rule of the room:** never say "as you can see". Show it, then say what it means.

Timings below are cumulative marks. Bracketed lines are what you *do*; quoted lines are what you *say*.

---

### 0:00 — 0:06 · Landing

*[Open API Galaxy. Landing page, nothing loaded.]*

> "This is API Galaxy. It runs entirely on your machine, and it turns a pile of OpenAPI specs into
> something you can actually reason about."

*[Click **Explore the Demo Galaxy**.]*

---

### 0:06 — 0:16 · The galaxy assembles

*[Seven specs load. Domains fly into position and settle into clusters.]*

> "Seven services, seven domains — Customer, Catalog, Cart, Order, Payment, Inventory, Shipping. This is
> NovaCart, a fictional retailer we ship with the product. Thirty-two operations, and none of this was
> hand-drawn. It came out of the specs."

*[Let the layout settle for a beat. Do not talk over the animation.]*

---

### 0:16 — 0:26 · Counts, observed vs inferred

*[Point at the stats strip: 7 services · 32 operations · 9 observed edges · 6 inferred edges.]*

> "Nine of these edges are *observed* — they're declared in the specs as explicit dependencies. Six are
> *inferred*: API Galaxy read the field names and the prose and worked out that two teams are describing
> the same thing under different names. Solid lines are facts. Dashed lines are the model's reading."

*[Toggle **Inferred** off, then on. The dashed edges vanish and return.]*

> "You can always see which is which. That's the whole trust model."

---

### 0:26 — 0:40 · Play the Place Order journey

*[Open the Journeys panel. Click **Place Order**. Press play.]*

*[Six steps light up in sequence: getCart → getCustomer → placeOrder → reserveInventory →
authorizePayment → getOrder.]*

> "Here's checkout, animated across four domains. Read the basket, check the shopper isn't blocked, write
> the order, hold the stock, authorize the card. If any one of those fails, nothing gets written."

*[Pause on the `authorizePayment` step.]*

> "Watch the shopper identifier. It leaves the cart as `customer_id`, arrives at the order as `cust_no`,
> and reaches the payment as `party_key`. Same person. Three names. Nobody wrote that down anywhere."

---

### 0:40 — 0:50 · Ask it a question

*[Open the Ask panel. Type: **How does checkout work?** Send.]*

*[Answer streams in with inline citations back to specific operations.]*

> "The answer is grounded — every claim links back to the operation it came from. And it flags the thing
> nobody wants to hear: your documented checkout route is marked deprecated, and everyone's still calling it."

---

### 0:50 — 1:02 · Break Lab

*[Open **Break Lab**. Select `customer-api` → `Customer.customer_id`. Rename to `party_id`. Apply.]*

*[Shockwave animation propagates outward from Customer through Cart, Order, Payment.]*

> "Let's break it. Rename `customer_id` to `party_id` — a one-line change one team could ship on a Tuesday."

*[Impact panel resolves: 4 services, 11 operations, 3 journeys affected.]*

> "Four services. Three of the six journeys. Including checkout. That's the blast radius of a rename,
> before anyone writes the migration ticket."

---

### 1:02 — 1:12 · Repair and replay

*[Click **Apply suggested repair** — add a canonical alias mapping rather than renaming back.]*

> "The repair isn't 'undo'. It's declaring the alias properly so the graph knows these three names are one
> concept."

*[Replay the **Place Order** journey. It runs clean, green end to end.]*

> "Replay checkout. Clean."

---

### 1:12 — 1:20 · Model Arena

*[Open **Model Arena**. Two enrichment runs side by side on the same estate.]*

> "Different models read the same specs differently. The Arena runs them head to head and scores each
> against the estate's reference ontology — so 'which model should I trust here' is a measurement, not a vibe."

---

### 1:20 — 1:30 · Exports

*[Click **Export → SVG**. Then **Export → Mermaid**, showing the text diff-able output.]*

> "Export the graph as SVG for the deck, or as Mermaid so your architecture diagram lives in git and shows
> up in code review."

*[Click **Export → PDF**, then **Export → Interactive HTML**.]*

> "Or take the whole thing with you: a PDF for the architecture review, and a single self-contained HTML
> file your colleagues can open and explore without installing anything."

*[Land on the assembled galaxy view.]*

> "Seven specs in. A map, a risk register and an answer to 'what breaks if I change this' out. Locally,
> in about a minute."

---

## Timing cheat sheet

| Mark | Beat | Budget |
|---|---|---|
| 0:00 | Landing, click Explore | 6s |
| 0:06 | Domains assemble | 10s |
| 0:16 | Counts, observed vs inferred toggle | 10s |
| 0:26 | Play Place Order journey | 14s |
| 0:40 | Ask "How does checkout work?" | 10s |
| 0:50 | Break Lab rename, shockwave, impact | 12s |
| 1:02 | Apply repair, replay checkout | 10s |
| 1:12 | Model Arena compare | 8s |
| 1:20 | Export SVG + Mermaid + PDF + HTML | 10s |
| **1:30** | **Total** | **90s** |

**If you need to land at 60 seconds:** cut Model Arena entirely and compress the exports to a single
"export as PDF or interactive HTML" line. Never cut the Break Lab shockwave — it is the moment the demo
earns its keep.
