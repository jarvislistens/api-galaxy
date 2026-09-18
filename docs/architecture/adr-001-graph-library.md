# ADR 001 — Cytoscape.js for graph visualisation

**Status:** accepted · 2026-09-19

## Context

The graph is the product. Whatever renders it has to do five things:

1. lay out a few hundred nodes without a hairball, and stay responsive at ~1,000;
2. express *semantic zoom* — four levels from business capability down to field;
3. run **headless**, because the exported HTML report must render the same graph with no
   React and no backend;
4. export SVG and PNG at presentation resolution;
5. let us encode meaning in shape and stroke, not only colour.

The two realistic options were React Flow and Cytoscape.js.

## Decision

**Cytoscape.js**, with the `fcose` layout extension.

## Why

| Requirement | Cytoscape.js | React Flow |
| --- | --- | --- |
| Layouts | `fcose`, `breadthfirst`, `concentric`, `grid` built in | none; you bring dagre/elk and wire it yourself |
| Headless | first-class — `cytoscape({ headless: true })` | needs a DOM |
| SVG / PNG export | `cy.png()` native; SVG via extension or our own renderer | screenshot the DOM |
| Styling | a selector-based stylesheet, so shape/stroke/colour are data-driven | React components per node |
| 1,000 nodes | canvas renderer, fine | one DOM node each, degrades |

React Flow produces nicer *custom* nodes and is pleasanter to write when each node is a
small React component. That is a real advantage for a flow builder. It is the wrong trade
here: we have eighteen node types that differ by shape and stroke rather than by content,
and we would have paid for the flexibility in layout wiring and export plumbing we do not
want to own.

The headless requirement was decisive. The interactive HTML export has to work from a
`file://` URL with no CDN, no backend and no React runtime.

## Consequences

* Node appearance is declared once in `apps/web/src/components/graph/graph-style.ts` and
  consumed by the app, so the visual contract has a single source of truth.
* The layout runs **once per data change** and then stops. Physics that keeps nudging
  nodes after the user has oriented themselves is actively hostile, so highlighting,
  journey playback and impact shading only add and remove CSS classes — positions never
  move as a result of a selection.
* Cytoscape's canvas is opaque to assistive technology. We therefore ship
  `GraphNodeList`, a real focusable list of the same data, beside every canvas. That is a
  hard requirement, not a nicety — see ADR 003 and the accessibility section of the README.
* The exported report re-implements pan/zoom on a static SVG rather than embedding
  Cytoscape, because shipping the library inside every report would add ~400 KB to each
  file for behaviour a 3 KB script covers.

## Alternatives considered

* **D3 directly** — maximum control, but we would be writing a layout engine and a
  hit-testing layer. Not a good use of the time.
* **Graphviz server-side, image client-side** — excellent static layout, but it gives up
  interaction entirely, and interaction is the point.
* **Sigma.js / WebGL** — faster above ~10,000 nodes. We cap a view at 5,000 and cluster
  above that, so the extra speed would buy nothing and cost styling expressiveness.
