# Try it on your own import

Two small specifications — **PawStay**, a pet boarding business — for testing the
*import* path rather than the bundled demo. Together they are 8 operations and 9 schemas,
small enough to read in a couple of minutes.

They are seeded with eight problems. Seven were planted deliberately; the eighth API
Galaxy found on its own, and it was right.

## Run it

Start the app, then go to **Import your API** (or http://127.0.0.1:3000/import).

Drag **both** files in at once — `booking-api.yaml` and `billing-api.yaml`. Importing them
together is the point: three of the eight findings only exist *between* the two services,
and you cannot see them one file at a time.

You can also paste one into the **Paste** tab to watch validation run as you type. Try
deleting a closing brace to see the error point at the line.

## What it should find

Thirteen findings, in this order of severity:

| Severity | Kind | Finding | Why it is there |
| --- | --- | --- | --- |
| high | heuristic | `'amount'` has different types in different services | `Booking.total_amount` is a JSON `number`; `Invoice.amount` is a decimal `string`. The same money, two representations. |
| high | heuristic | Sensitive data exposed without authentication | `GET /public/owners/{ownerId}/card` sets `security: []` and returns `email` and `phone`. |
| medium | heuristic | `'owner'` is spelled 2 different ways | Booking says `owner_id`; Billing says `party_ref`. Nothing in either document links them. |
| medium | **proved** | Circular dependency between billing-api and booking-api | `confirmBooking` → `chargeInvoice` → `getBooking`. Valid, but awkward. |
| medium | **proved** | Deprecated operation still participates in a flow | `POST /bookings/{id}/confirm` is `deprecated: true` and is still the documented way to confirm. |
| medium | **proved** | Services return different error envelopes | `Error` (code/message) vs `Problem` (RFC 9457). |
| medium | heuristic | `Invoice` / `OwnerCard` / `Owner` carry personal data | Emails, phone numbers, `card_last4`. |
| low | heuristic | Pagination conventions differ | Booking uses `page`/`size`; Billing uses `limit`/`offset`. |
| low | **proved** | Schema `LegacyCoupon` is never used | Planted dead code. |
| low | **proved** | Schema `Owner` is never used | **Not planted.** The public endpoint returns `OwnerCard`, so `Owner` is defined and never referenced. A real bug in the example, found by the tool. |
| info | **proved** | 2 of 8 operations have no success example | — |

"Proved" findings are deterministic. "Heuristic" ones are judgements, and the UI labels
them that way everywhere.

## Then try the loop

**Ask** (the default engine uses no model at all):

- *What depends on `owner_id`?* → used by 8 operations across both services, **and it also
  appears as `party_ref`** — which is the answer you would not get from reading either file.
- *Which concepts have conflicting definitions?*
- *What looks risky?*

**Break Lab** → *Rename a field* → target `Booking.owner_id` → new name `customer_id`:

```
broken 4 · degraded 7 · possibly affected 23 · unaffected 60
2 of 3 journeys break
```

Note what appears in the broken list: **`party_ref`**, in the other service. The rename
reaches it through the inferred alias, which is exactly the class of breakage that gets
missed in review.

Then **Repair** → *Propose repairs* → apply either one and watch the journeys re-validate.
"Journey restored" only appears once validation actually passes.

**Reports** → export. All ten formats work on this project; the interactive HTML report
is ~330 KB and opens from the file with no backend.

## Make it your own

The fastest way to understand the rules is to break them:

- delete `security: []` from the public endpoint → the high-severity finding disappears
- rename `party_ref` to `owner_id` → the alias cluster disappears
- make `Invoice.amount` a `number` → the type-boundary finding disappears
- reference `Owner` from an operation → the orphan finding disappears

Re-import after each edit and compare. Every finding should have a cause you can point at
in the YAML — if one does not, that is a bug worth reporting.
