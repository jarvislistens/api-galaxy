/* API Galaxy interactive report — runtime.
 *
 * Plain ES2018, no modules, no bundler, no dependencies. The file is read off disk by
 * html_report.py and inlined into a single self-contained page, so anything that needed
 * npm or a network fetch would defeat the point of the export.
 *
 * Two rules run through the whole file:
 *
 * 1. Project data is untrusted. It came from OpenAPI documents someone else wrote, so
 *    every value reaches the DOM through textContent or createElement — never innerHTML,
 *    never insertAdjacentHTML, never a template string assigned to .innerHTML.
 * 2. Nothing leaves the page. There is no fetch, no XHR, no beacon, no external asset.
 *    The report is readable from a USB stick on a machine with the network unplugged.
 */
(function () {
  "use strict";

  var dataNode = document.getElementById("api-galaxy-data");
  if (!dataNode) return;

  var DATA;
  try {
    DATA = JSON.parse(dataNode.textContent);
  } catch (err) {
    return;
  }

  var NODES = DATA.nodes || {};
  var ORDER = DATA.nodeOrder || [];
  var ADJ = DATA.adjacency || {};
  var JOURNEYS = DATA.journeys || [];
  var reduceMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }
  function $$(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  /* ------------------------------------------------------------------ tabs */

  function initTabs() {
    var tabs = $$(".ag-tab");
    if (!tabs.length) return;

    function activate(tab, focus) {
      tabs.forEach(function (candidate) {
        var selected = candidate === tab;
        candidate.setAttribute("aria-selected", selected ? "true" : "false");
        candidate.tabIndex = selected ? 0 : -1;
        var panel = document.getElementById(candidate.getAttribute("aria-controls"));
        if (panel) panel.hidden = !selected;
      });
      if (focus) tab.focus();
    }

    tabs.forEach(function (tab, index) {
      tab.addEventListener("click", function () {
        activate(tab, false);
      });
      tab.addEventListener("keydown", function (event) {
        var delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (!delta) return;
        event.preventDefault();
        activate(tabs[(index + delta + tabs.length) % tabs.length], true);
      });
    });
    activate(tabs[0], false);
  }

  /* ------------------------------------------------------------------ graph */

  var view = { scale: 1, x: 0, y: 0 };
  var svg = null;
  var viewport = null;
  var canvas = null;
  var selectedId = null;

  function applyTransform() {
    if (!viewport) return;
    viewport.setAttribute(
      "transform",
      "translate(" + view.x.toFixed(2) + "," + view.y.toFixed(2) + ") scale(" +
        view.scale.toFixed(4) + ")"
    );
    var readout = $("#ag-zoom-readout");
    if (readout) readout.textContent = Math.round(view.scale * 100) + "%";
  }

  function zoomBy(factor, originX, originY) {
    var next = Math.min(6, Math.max(0.15, view.scale * factor));
    if (originX === undefined) {
      var box = canvas.getBoundingClientRect();
      originX = box.width / 2;
      originY = box.height / 2;
    }
    // Keep the point under the cursor fixed while the scale changes.
    var ratio = next / view.scale;
    view.x = originX - ratio * (originX - view.x);
    view.y = originY - ratio * (originY - view.y);
    view.scale = next;
    applyTransform();
  }

  function fitToView() {
    view.scale = 1;
    view.x = 0;
    view.y = 0;
    applyTransform();
  }

  function initGraph() {
    canvas = $("#ag-canvas");
    if (!canvas) return;
    svg = $("svg", canvas);
    if (!svg) return;
    viewport = $(".ag-viewport", svg);
    if (!viewport) return;

    var dragging = false;
    var startX = 0;
    var startY = 0;

    canvas.addEventListener("pointerdown", function (event) {
      if (event.target.closest && event.target.closest(".ag-node")) return;
      dragging = true;
      startX = event.clientX - view.x;
      startY = event.clientY - view.y;
      canvas.classList.add("is-panning");
      if (canvas.setPointerCapture) canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", function (event) {
      if (!dragging) return;
      view.x = event.clientX - startX;
      view.y = event.clientY - startY;
      applyTransform();
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach(function (name) {
      canvas.addEventListener(name, function () {
        dragging = false;
        canvas.classList.remove("is-panning");
      });
    });
    canvas.addEventListener(
      "wheel",
      function (event) {
        if (!event.ctrlKey && Math.abs(event.deltaY) < 2) return;
        event.preventDefault();
        var box = canvas.getBoundingClientRect();
        zoomBy(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX - box.left, event.clientY - box.top);
      },
      { passive: false }
    );

    var zoomIn = $("#ag-zoom-in");
    var zoomOut = $("#ag-zoom-out");
    var zoomFit = $("#ag-zoom-fit");
    if (zoomIn) zoomIn.addEventListener("click", function () { zoomBy(1.25); });
    if (zoomOut) zoomOut.addEventListener("click", function () { zoomBy(1 / 1.25); });
    if (zoomFit) zoomFit.addEventListener("click", fitToView);

    // Arrow keys pan the canvas when it holds focus, so the graph is usable without a
    // pointing device.
    canvas.tabIndex = 0;
    canvas.addEventListener("keydown", function (event) {
      var step = event.shiftKey ? 120 : 40;
      var handled = true;
      if (event.key === "ArrowLeft") view.x += step;
      else if (event.key === "ArrowRight") view.x -= step;
      else if (event.key === "ArrowUp") view.y += step;
      else if (event.key === "ArrowDown") view.y -= step;
      else if (event.key === "+" || event.key === "=") zoomBy(1.2);
      else if (event.key === "-" || event.key === "_") zoomBy(1 / 1.2);
      else if (event.key === "0") fitToView();
      else handled = false;
      if (handled) {
        event.preventDefault();
        applyTransform();
      }
    });

    $$(".ag-node", svg).forEach(function (group) {
      var id = group.getAttribute("data-node-id");
      group.addEventListener("click", function () { selectNode(id); });
      group.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectNode(id);
        }
      });
    });

    applyTransform();
  }

  /* ------------------------------------------------------------- inspector */

  function sourceChip(record) {
    var chip = el("span", "ag-chip", record.sourceLabel || record.sourceKind || "unknown");
    chip.setAttribute("data-kind", record.sourceKind || "unknown");
    return chip;
  }

  function selectNode(id) {
    var record = NODES[id];
    var panel = $("#ag-inspector");
    if (!panel) return;
    selectedId = record ? id : null;

    $$(".ag-node", document).forEach(function (group) {
      group.classList.toggle("is-selected", group.getAttribute("data-node-id") === selectedId);
    });

    clear(panel);
    if (!record) {
      panel.appendChild(el("p", "ag-empty", "Select a node in the map to inspect it."));
      return;
    }

    panel.appendChild(el("h3", null, record.label));
    var meta = el("p");
    meta.appendChild(el("span", "ag-chip", record.type));
    meta.appendChild(sourceChip(record));
    if (record.acceptance && record.acceptance !== "observed") {
      meta.appendChild(el("span", "ag-chip", record.acceptance));
    }
    panel.appendChild(meta);

    if (record.description) {
      panel.appendChild(el("p", null, record.description));
    }

    panel.appendChild(el("h4", null, "Where this came from"));
    panel.appendChild(el("p", null, record.explanation || "No explanation recorded."));
    var details = el("ul");
    addDetail(details, "Source", record.sourceLabel);
    addDetail(details, "Confidence", record.confidence === null || record.confidence === undefined
      ? null
      : Math.round(record.confidence * 100) + "%");
    addDetail(details, "Provider", record.provider);
    addDetail(details, "Model", record.model);
    addDetail(details, "Rule", record.ruleId);
    addDetail(details, "Domain", record.domain);
    addDetail(details, "Service", record.service);
    if (details.childNodes.length) panel.appendChild(details);

    panel.appendChild(el("h4", null, "Evidence"));
    if (record.evidence && record.evidence.length) {
      var evidence = el("ul");
      record.evidence.forEach(function (item) {
        var li = el("li");
        li.appendChild(el("span", "ag-locator", item.locator));
        if (item.excerpt) {
          li.appendChild(document.createElement("br"));
          li.appendChild(document.createTextNode(item.excerpt));
        }
        evidence.appendChild(li);
      });
      panel.appendChild(evidence);
    } else {
      panel.appendChild(el("p", "ag-empty", "No source locator was recorded for this node."));
    }

    var neighbours = ADJ[id] || [];
    panel.appendChild(el("h4", null, "Connected to (" + neighbours.length + ")"));
    if (!neighbours.length) {
      panel.appendChild(el("p", "ag-empty", "Nothing links to this node in the current scope."));
      return;
    }
    var list = el("ul");
    neighbours.slice(0, 60).forEach(function (entry) {
      var other = NODES[entry.id];
      if (!other) return;
      var li = el("li");
      var button = el("button", "ag-link-btn", other.label);
      button.type = "button";
      button.setAttribute(
        "aria-label",
        "Inspect " + other.label + ", " + entry.direction + " " + entry.label
      );
      button.addEventListener("click", function () { selectNode(entry.id); });
      li.appendChild(button);
      li.appendChild(document.createTextNode(" "));
      li.appendChild(el("span", "ag-locator", entry.direction + " " + entry.label));
      li.appendChild(document.createTextNode(" "));
      li.appendChild(sourceChip({ sourceKind: entry.sourceKind, sourceLabel: entry.sourceLabel }));
      list.appendChild(li);
    });
    panel.appendChild(list);
  }

  function addDetail(list, label, value) {
    if (value === null || value === undefined || value === "") return;
    var li = el("li");
    li.appendChild(el("strong", null, label + ": "));
    li.appendChild(document.createTextNode(String(value)));
    list.appendChild(li);
  }

  /* --------------------------------------------------------------- filters */

  var filters = { search: "", type: "", domain: "", provenance: "" };

  function matches(record) {
    if (filters.type && record.type !== filters.type) return false;
    if (filters.domain && record.domain !== filters.domain) return false;
    if (filters.provenance && record.provenanceGroup !== filters.provenance) return false;
    if (filters.search) {
      var needle = filters.search;
      var haystack = (record.label + " " + record.type + " " + (record.description || "") +
        " " + record.id).toLowerCase();
      if (haystack.indexOf(needle) === -1) return false;
    }
    return true;
  }

  function applyFilters() {
    var visible = {};
    var shown = 0;
    ORDER.forEach(function (id) {
      var record = NODES[id];
      if (!record) return;
      var ok = matches(record);
      visible[id] = ok;
      if (ok) shown += 1;
    });

    $$(".ag-node", document).forEach(function (group) {
      var id = group.getAttribute("data-node-id");
      var ok = visible[id] !== false;
      group.classList.toggle("is-hidden", !ok);
      group.classList.toggle("is-match", ok && Boolean(filters.search));
    });
    $$(".ag-edge", document).forEach(function (path) {
      var a = path.getAttribute("data-source");
      var b = path.getAttribute("data-target");
      path.classList.toggle("is-hidden", visible[a] === false || visible[b] === false);
    });

    var readout = $("#ag-filter-count");
    if (readout) {
      readout.textContent = shown + " of " + ORDER.length + " nodes match";
    }
    renderResults(visible);
  }

  function renderResults(visible) {
    var list = $("#ag-results");
    if (!list) return;
    clear(list);
    var count = 0;
    for (var i = 0; i < ORDER.length && count < 200; i += 1) {
      var id = ORDER[i];
      if (visible[id] === false) continue;
      var record = NODES[id];
      if (!record) continue;
      count += 1;
      var li = el("li");
      var button = el("button", "ag-link-btn", record.label);
      button.type = "button";
      button.addEventListener("click", makeSelector(id));
      li.appendChild(button);
      li.appendChild(document.createTextNode(" "));
      li.appendChild(el("span", "ag-locator", record.type));
      list.appendChild(li);
    }
  }

  function makeSelector(id) {
    return function () {
      selectNode(id);
    };
  }

  function initFilters() {
    var search = $("#ag-search");
    var type = $("#ag-filter-type");
    var domain = $("#ag-filter-domain");
    var provenance = $("#ag-filter-provenance");
    var reset = $("#ag-filter-reset");

    if (search) {
      search.addEventListener("input", function () {
        filters.search = search.value.trim().toLowerCase();
        applyFilters();
      });
    }
    if (type) {
      type.addEventListener("change", function () {
        filters.type = type.value;
        applyFilters();
      });
    }
    if (domain) {
      domain.addEventListener("change", function () {
        filters.domain = domain.value;
        applyFilters();
      });
    }
    if (provenance) {
      provenance.addEventListener("change", function () {
        filters.provenance = provenance.value;
        applyFilters();
      });
    }
    if (reset) {
      reset.addEventListener("click", function () {
        filters = { search: "", type: "", domain: "", provenance: "" };
        if (search) search.value = "";
        if (type) type.value = "";
        if (domain) domain.value = "";
        if (provenance) provenance.value = "";
        applyFilters();
      });
    }
    applyFilters();
  }

  /* -------------------------------------------------------- journey player */

  var player = { journey: null, index: 0, timer: null, speed: 1 };

  function highlightStep(step) {
    var wanted = {};
    (step ? step.nodeIds || [] : []).forEach(function (id) {
      wanted[id] = true;
    });
    $$(".ag-node", document).forEach(function (group) {
      group.classList.toggle(
        "is-active-step",
        Boolean(step) && wanted[group.getAttribute("data-node-id")] === true
      );
    });
  }

  function renderStep() {
    var box = $("#ag-step");
    if (!box) return;
    clear(box);
    if (!player.journey) {
      box.appendChild(el("p", "ag-empty", "Choose a journey and press Play."));
      highlightStep(null);
      return;
    }
    var step = player.journey.steps[player.index];
    if (!step) return;

    box.appendChild(
      el("p", "ag-step-title", "Step " + step.order + " of " + player.journey.steps.length +
        " — " + step.label)
    );
    box.appendChild(el("p", "ag-step-narration", step.narration || ""));
    if (step.technical) box.appendChild(el("p", "ag-step-detail", step.technical));

    var bar = $("#ag-progress-bar");
    if (bar) {
      var pct = ((player.index + 1) / player.journey.steps.length) * 100;
      bar.style.width = pct.toFixed(1) + "%";
    }
    var live = $("#ag-player-live");
    if (live) live.textContent = "Step " + step.order + ": " + step.label;
    highlightStep(step);
  }

  function stopPlayback() {
    if (player.timer) {
      window.clearInterval(player.timer);
      player.timer = null;
    }
    var play = $("#ag-play");
    if (play) {
      play.setAttribute("aria-pressed", "false");
      play.textContent = "Play";
    }
  }

  function startPlayback() {
    if (!player.journey || player.timer) return;
    var play = $("#ag-play");
    if (play) {
      play.setAttribute("aria-pressed", "true");
      play.textContent = "Pause";
    }
    // Reduced motion still advances — it is information, not decoration — but slowly
    // enough that nothing flickers.
    var interval = (reduceMotion ? 5200 : 2600) / player.speed;
    player.timer = window.setInterval(function () {
      if (player.index >= player.journey.steps.length - 1) {
        stopPlayback();
        return;
      }
      player.index += 1;
      renderStep();
    }, interval);
  }

  function selectJourney(id) {
    stopPlayback();
    player.journey = null;
    for (var i = 0; i < JOURNEYS.length; i += 1) {
      if (JOURNEYS[i].id === id) player.journey = JOURNEYS[i];
    }
    player.index = 0;
    renderStep();
  }

  function initPlayer() {
    var picker = $("#ag-journey");
    if (picker) {
      picker.addEventListener("change", function () {
        selectJourney(picker.value);
      });
    }
    var play = $("#ag-play");
    if (play) {
      play.addEventListener("click", function () {
        if (player.timer) stopPlayback();
        else startPlayback();
      });
    }
    var step = $("#ag-step-forward");
    if (step) {
      step.addEventListener("click", function () {
        stopPlayback();
        if (player.journey && player.index < player.journey.steps.length - 1) {
          player.index += 1;
          renderStep();
        }
      });
    }
    var back = $("#ag-step-back");
    if (back) {
      back.addEventListener("click", function () {
        stopPlayback();
        if (player.journey && player.index > 0) {
          player.index -= 1;
          renderStep();
        }
      });
    }
    var restart = $("#ag-restart");
    if (restart) {
      restart.addEventListener("click", function () {
        stopPlayback();
        player.index = 0;
        renderStep();
      });
    }
    var speed = $("#ag-speed");
    if (speed) {
      speed.addEventListener("change", function () {
        player.speed = parseFloat(speed.value) || 1;
        if (player.timer) {
          stopPlayback();
          startPlayback();
        }
      });
    }
    if (picker && picker.value) selectJourney(picker.value);
    else renderStep();
  }

  /* ------------------------------------------------------------------ boot */

  function boot() {
    initTabs();
    initGraph();
    initFilters();
    initPlayer();
    selectNode(null);
    var status = $("#ag-runtime-status");
    if (status) {
      status.textContent =
        "Interactive mode ready — " + ORDER.length + " nodes loaded from this file.";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
