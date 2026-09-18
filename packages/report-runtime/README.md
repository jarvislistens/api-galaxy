# report-runtime

The CSS and JavaScript for API Galaxy's interactive HTML report.

## There is deliberately no build step

`src/report.css` and `src/report.js` are plain, hand-written files. There is no
`package.json`, no `node_modules`, no bundler, no transpiler and no npm install.

That is a decision, not an omission:

- **The output must be a single file with zero external requests.** The report is meant
  to be emailed, dropped on a share, opened from a USB stick, or read on an air-gapped
  machine. A bundler that emits a chunk graph, a CDN import, or a webfont would break the
  one property that makes the artifact useful.
- **The exporter inlines these files at render time.**
  `apps/api/api_galaxy/exports/html_report.py` reads both files off disk and embeds them
  in a `<style>` and a `<script>` block. Editing this directory changes the next report;
  nothing needs to be compiled first.
- **Disk and install time are constrained.** A toolchain for two files that total a few
  tens of kilobytes is not worth hundreds of megabytes of dependencies.

`report.js` is therefore written in ES2018 that every current browser parses directly:
no modules, no JSX, no optional chaining, no top-level `await`.

## Contract with the exporter

`html_report.py` authors the static page structure and writes the project data into one
`<script type="application/json" id="api-galaxy-data">` block. `report.js` reads that
block and wires up behaviour. The two sides agree on these hooks:

| Hook | Purpose |
| --- | --- |
| `#api-galaxy-data` | JSON payload: `nodes`, `nodeOrder`, `adjacency`, `journeys`, `project`, `legend` |
| `.ag-tab` / `[aria-controls]` | Tab buttons and the panels they show |
| `#ag-canvas` | Container holding the embedded SVG map |
| `.ag-viewport` (inside the SVG) | The `<g>` that pan and zoom apply a `transform` to |
| `.ag-node[data-node-id]` | Clickable/focusable node groups in the SVG |
| `.ag-edge[data-source][data-target]` | Edge paths, dimmed when either end is filtered out |
| `#ag-search`, `#ag-filter-*`, `#ag-filter-reset` | Filter controls |
| `#ag-results`, `#ag-filter-count` | Filter results list and counter |
| `#ag-inspector` | Node inspector panel |
| `#ag-journey`, `#ag-play`, `#ag-step-back`, `#ag-step-forward`, `#ag-restart`, `#ag-speed` | Journey player controls |
| `#ag-step`, `#ag-progress-bar`, `#ag-player-live` | Journey player output |
| `#ag-zoom-in`, `#ag-zoom-out`, `#ag-zoom-fit`, `#ag-zoom-readout` | Zoom controls |

## Rules for changing these files

1. **Never build DOM from project data with `innerHTML`.** Labels and descriptions come
   from third-party OpenAPI documents. Use `textContent` and `createElement`. The export
   tests assert that a node labelled `<script>alert(1)</script>` renders as text.
2. **Never add a network call.** No `fetch`, no `XMLHttpRequest`, no `new Image().src`,
   no `<link>`, no `@import`, no webfont. The tests grep the rendered report for
   `http://`, `https://`, `//cdn`, `<script src` and `<link rel="stylesheet"`.
3. **Keep it keyboard-usable.** Every control is a real `<button>`, `<select>` or
   `<input>` with a label or `aria-label`, focus is visible, and the graph canvas pans
   with the arrow keys.
4. **Respect `prefers-reduced-motion`.** Transitions are disabled and the journey player
   slows down rather than animating.
5. **Keep the print stylesheet working.** The report is frequently printed; `@media
   print` reveals every tab panel and switches to a light palette.
