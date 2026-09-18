# NovaCart — the bundled API Galaxy demo estate

NovaCart is a **completely fictional** online retailer. Nothing in this folder describes a real company,
a real system or a real person. Every host is under `api.novacart.example`, every identifier is invented,
every shopper is made up, and the two credentials in the Postman collection are obvious placeholders.

The estate exists for one reason: to give API Galaxy something honest to chew on. Seven OpenAPI 3.0.3
specs, thirty-two operations, six end-to-end journeys — and **nine deliberate design defects** planted so
the graph builder, the risk rules and the AI enrichment pass all have real findings to surface rather
than a suspiciously clean demo.

---

## The seven services

| Service | Domain | What it owns | Ops | Auth | Error shape | Pagination |
|---|---|---|---|---|---|---|
| `customer-api.yaml` | Customer | Shopper identity, contact details, loyalty tier, saved addresses | 6 | `bearerAuth` (JWT) | `Error` | `page` + `size` |
| `catalog-api.yaml` | Catalog | Published products, category tree, keyword search | 4 | `apiKeyAuth` (`X-API-Key`) | `Error` | `limit` + `offset`, plus `cursor` on search |
| `cart-api.yaml` | Cart | The in-progress basket and the handover into checkout | 5 | `bearerAuth` (JWT) | `ProblemResponse` | n/a |
| `order-api.yaml` | Order | The order book: placement, retrieval, cancellation | 4 | `bearerAuth` (JWT) | `ProblemResponse` | `page` + `size` |
| `payment-api.yaml` | Payment | Authorization, capture and refund of money | 4 | `bearerAuth` (JWT) | `ProblemResponse` | n/a |
| `inventory-api.yaml` | Inventory | Warehouse stock positions and the reservation ledger | 5 | `bearerAuth` (JWT) | `Error` | `limit` + `offset` |
| `shipping-api.yaml` | Shipping | Carrier bookings, tracking numbers, parcel scans | 4 | `bearerAuth` (JWT) | `ProblemResponse` | `page` + `size` |

Each spec carries `x-api-galaxy-domain` at its root so the loader can colour the graph without guessing.

## The six journeys

Defined formally in `expected-journeys.json`:

1. **Register Customer** — `createCustomer` → `getCustomer` → `listCustomerAddresses`
2. **Search and Add Product to Cart** — `searchProducts` → `getProduct` → `createCart` → `addCartItem` → `getCart`
3. **Place Order** — `getCart` → `getCustomer` → `placeOrder` → `reserveInventory` → `authorizePayment` → `getOrder`
4. **Complete Payment** — `getOrder` → `capturePayment` → `getPayment`
5. **Reserve Inventory** — `getInventory` → `reserveInventory` → `getOrder` → `commitReservation` → `listReservations`
6. **Create Shipment and Track Delivery** — `getOrder` → `commitReservation` → `createShipment` → `getShipmentTracking` → `getShipment`

Journey 3 is the demo's centrepiece: it crosses four domains and drags the customer identifier through
three different field names on the way.

## How dependencies are encoded

Operations declare their cross-service calls with the vendor extension `x-api-galaxy-depends-on`:

```yaml
x-api-galaxy-depends-on:
  - service: customer-api
    operationId: getCustomer
    reason: Validates the customer exists and is not blocked before the order is accepted.
```

There are **nine explicit edges** in the estate, all statically parseable:

| From | To | Why |
|---|---|---|
| `order-api:placeOrder` | `customer-api:getCustomer` | Validate the shopper before accepting the order |
| `order-api:placeOrder` | `cart-api:getCart` | Freeze the exact lines and subtotal |
| `order-api:placeOrder` | `inventory-api:reserveInventory` | Hold stock for every SKU |
| `order-api:placeOrder` | `payment-api:authorizePayment` | Authorize the card for the total |
| `cart-api:checkoutCart` | `order-api:placeOrder` | Deprecated basket-to-order handover |
| `shipping-api:createShipment` | `order-api:getOrder` | Read lines and destination |
| `shipping-api:createShipment` | `inventory-api:commitReservation` | Firm up the allocation before picking |
| `inventory-api:commitReservation` | `order-api:getOrder` | Confirm the order is still live |
| `payment-api:capturePayment` | `order-api:getOrder` | Confirm the capture amount |

**And exactly one relationship that is deliberately *not* declared.** Shipping's `destination` object is
the same business concept as the Customer API's `Address` schema — same `line1`, `line2`, `city`, `region`,
`postal_code`, `country`, same meanings, same prose. There is no `$ref`, no shared component and no
`x-api-galaxy-depends-on` linking them. Static parsing will never find it. Only a semantic read of the
field names and descriptions can, which is precisely what the AI enrichment pass is there to prove.
That is defect #9, and the reference answer for it lives in `expected-ontology.json` as a relationship
with `"kind": "inferable"`.

---

## The nine intentional teaching defects

| # | Defect | Severity | File and location |
|---|---|---|---|
| 1 | **Alias ambiguity** — one customer concept, three field names. `customer_id` (Customer, Cart) becomes `cust_no` (Order) becomes `party_key` (Payment), with nothing in any contract stating they are the same thing. | high | `customer-api.yaml#/components/schemas/Customer/properties/customer_id`<br>`order-api.yaml#/components/schemas/Order/properties/cust_no`<br>`payment-api.yaml#/components/schemas/Payment/properties/party_key` |
| 2 | **Weakly secured endpoint exposing sensitive data** — the public shopper summary sets `security: []`, overriding the root `bearerAuth`, yet still returns `email`, `phone` and `loyalty_tier`. | high | `customer-api.yaml#/paths/~1public~1customers~1{customerId}~1summary/get`<br>schema at `customer-api.yaml#/components/schemas/CustomerSummary` |
| 3 | **Customer identifier crosses more than one service boundary during checkout** — the Place Order journey reads `customer_id` off the cart, posts it to the order as `cust_no` and forwards it to the payment as `party_key`. Three services, three names, one unrecorded coupling. | high | `cart-api.yaml#/components/schemas/Cart/properties/customer_id`<br>`order-api.yaml#/components/schemas/PlaceOrderRequest/properties/cust_no`<br>`payment-api.yaml#/components/schemas/AuthorizePaymentRequest/properties/party_key` |
| 4 | **Inconsistent error models** — Customer, Catalog and Inventory return `{code, message, details}`; Cart, Order, Payment and Shipping return an RFC 7807 problem document `{type, title, status, detail, instance}`. One checkout, two error handlers. | medium | `customer-api.yaml#/components/schemas/Error`<br>`catalog-api.yaml#/components/schemas/Error`<br>`inventory-api.yaml#/components/schemas/Error`<br>vs `order-api.yaml#/components/schemas/ProblemResponse` (and the same in `cart-api.yaml`, `payment-api.yaml`, `shipping-api.yaml`) |
| 5 | **Type change across a service boundary** — the same money value is `type: number, format: double` on the order and `type: string, format: decimal` on the payment. | high | `order-api.yaml#/components/schemas/Order/properties/total_amount`<br>`payment-api.yaml#/components/schemas/Payment/properties/amount` |
| 6 | **Deprecated operation still on the critical path** — `POST /carts/{cartId}/checkout` is marked `deprecated: true`, but its own description admits the storefront and the published integration guide still use it, and it is the only operation that converts a basket into an order for the caller. | medium | `cart-api.yaml#/paths/~1carts~1{cartId}~1checkout/post` (`deprecated: true`) |
| 7 | **Circular dependency between Order and Inventory** — `placeOrder` depends on `reserveInventory`, and `commitReservation` depends back on `getOrder`. Both specs are individually valid; together they form a two-service cycle. | medium | `order-api.yaml#/paths/~1orders/post/x-api-galaxy-depends-on/2`<br>`inventory-api.yaml#/paths/~1reservations~1{reservationId}~1commit/post/x-api-galaxy-depends-on/0` |
| 8 | **Divergent pagination** — three styles in one estate: `page`+`size` (Customer, Order, Shipping), `limit`+`offset` (Catalog, Inventory) and an opaque `cursor` (catalogue search). The response envelopes differ too. | medium | `customer-api.yaml#/components/parameters/PageParam`<br>`catalog-api.yaml#/components/parameters/LimitParam`<br>`catalog-api.yaml#/components/parameters/CursorParam`<br>`inventory-api.yaml#/components/parameters/LimitParam` |
| 9 | **Inferable-only relationship** — Shipping's `destination` is semantically the Customer API's `Address`, with no `$ref`, no shared schema and no declared dependency. Invisible to a parser, obvious to a reader. | low | `shipping-api.yaml#/components/schemas/Shipment/properties/destination`<br>`shipping-api.yaml#/components/schemas/CreateShipmentRequest/properties/destination`<br>`customer-api.yaml#/components/schemas/Address` |

### One defect-adjacent extra

`LegacyPromoCode` in `catalog-api.yaml#/components/schemas/LegacyPromoCode` is a **deliberately orphaned
schema** — defined, documented, and referenced by absolutely nothing. It is not one of the nine teaching
defects; it is there so the orphaned-schema rule has exactly one honest hit and can be demonstrated
without faking a finding.

### Two rules that should find nothing

`expected-risks.json` also records two control cases with `"expected_hits": 0`:

- **broken-reference** — every `$ref` in all seven specs resolves.
- **duplicate-operation-id** — all thirty-two `operationId` values are unique and camelCase.

If either of those ever reports a hit, the estate has drifted, not the product.

---

## PII markers

Fields are named so a PII dictionary can find them without heuristics: `email`, `phone`, `full_name`,
`date_of_birth`, `card_last4`. Realistic `format:` values (`email`, `date`, `date-time`) are attached
where they apply. Exactly two fields carry `x-api-galaxy-sensitive: true` — `date_of_birth` on the
Customer schemas and `card_last4` on `Payment` — so the difference between "matched the dictionary" and
"explicitly declared sensitive" is visible in the UI.

---

## What else is in this folder

| File | Purpose |
|---|---|
| `novacart-manifest.yaml` | Multi-file import manifest (`apiVersion: api-galaxy/v1`, `kind: EstateManifest`). Point API Galaxy at this to load all seven specs and their companions in one go. |
| `expected-journeys.json` | The six journeys with ordered steps and plain-language narration. Reference answer for journey detection. |
| `expected-risks.json` | Thirteen rule entries covering all nine defects, the orphan schema and the two zero-hit controls, each with JSON-pointer-ish locations. |
| `expected-ontology.json` | Domains, business entities with their aliases, capabilities and relationships split into `explicit` and `inferable`. The scoring target for AI enrichment. |
| `postman_collection.json` | Postman Collection v2.1.0, generated faithfully from the specs: one folder per service, one request per operation, `{{baseUrl}}` variables, example responses lifted from the spec examples. |
| `demo-script.md` | A 60–90 second narrated walkthrough with timings, from landing page to PDF export. |

## Verifying the estate

```bash
cd /Users/krishna8891/Documents/api-galaxy
python3 -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('samples/novacart/*.yaml')]; print('yaml ok')"
python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('samples/novacart/*.json')]; print('json ok')"
```

All seven specs are valid OpenAPI 3.0.3, every `$ref` resolves, every operation has a unique camelCase
`operationId` with a `summary`, a `description` and `tags`, every 2xx response with a body carries an
example, and every operation declares at least one error response in its own service's error envelope.
