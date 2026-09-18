"use client";

/**
 * The galaxy.
 *
 * Three columns: what to show on the left, the graph in the middle, why it is there on
 * the right. The canvas is never the only way to read the data — the same nodes are
 * always one keystroke away as a real list, because a canvas is opaque to a screen
 * reader and to anybody without a mouse.
 *
 * Two deliberate choices worth knowing about:
 *
 * 1. **The search is debounced, the input is not.** Typing updates the store instantly so
 *    the field feels direct; only the query waits, so a five-letter word is one request
 *    rather than five.
 * 2. **Expanded neighbours are merged client-side.** Double-clicking a node pulls two
 *    hops from the API and unions them into the current result, so exploring outward
 *    never loses the filters you set to get there.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Compass, List, Network, PanelRightOpen, SlidersHorizontal, X } from "lucide-react";
import { useParams } from "next/navigation";
import * as React from "react";
import {
  GraphCanvas,
  type GraphCanvasHandle,
  GraphNodeList,
} from "@/components/graph/graph-canvas";
import {
  CanvasControls,
  type FilterOption,
  GraphFilters,
  LayoutPicker,
  SemanticZoom,
  ZOOM_LEVELS,
} from "@/components/graph/graph-controls";
import { GraphLegend } from "@/components/graph/graph-legend";
import { Minimap } from "@/components/graph/minimap";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Skeleton,
  Tooltip,
  cx,
} from "@/components/ui/primitives";
import { Inspector } from "@/components/workspace/inspector";
import { InspectorRail, PageHeader } from "@/components/workspace/shell";
import { api, ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { GraphEdge, GraphNode } from "@/lib/types";

/** Above this, the inspector is a column. Below it, a drawer. */
const WIDE = "(min-width: 1100px)";
const MAX_NODES = 1200;
const SEARCH_DEBOUNCE_MS = 180;

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();

  const zoom = useWorkspace((s) => s.zoom);
  const setZoom = useWorkspace((s) => s.setZoom);
  const domainFilter = useWorkspace((s) => s.domainFilter);
  const setDomainFilter = useWorkspace((s) => s.setDomainFilter);
  const serviceFilter = useWorkspace((s) => s.serviceFilter);
  const setServiceFilter = useWorkspace((s) => s.setServiceFilter);
  const includeInferred = useWorkspace((s) => s.includeInferred);
  const setIncludeInferred = useWorkspace((s) => s.setIncludeInferred);
  const graphSearch = useWorkspace((s) => s.graphSearch);
  const setGraphSearch = useWorkspace((s) => s.setGraphSearch);
  const layout = useWorkspace((s) => s.layout);
  const setLayout = useWorkspace((s) => s.setLayout);
  const selectedNodeId = useWorkspace((s) => s.selectedNodeId);
  const select = useWorkspace((s) => s.select);
  const selectEdge = useWorkspace((s) => s.selectEdge);
  const highlight = useWorkspace((s) => s.highlight);
  const clearHighlight = useWorkspace((s) => s.clearHighlight);
  const scenarioId = useWorkspace((s) => s.activeScenarioId);
  const toast = useWorkspace((s) => s.toast);

  const canvasRef = React.useRef<GraphCanvasHandle | null>(null);
  const wide = useMediaQuery(WIDE);

  const [view, setView] = React.useState<"graph" | "list">("graph");
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [filtersOpen, setFiltersOpen] = React.useState(false);
  const [focused, setFocused] = React.useState(false);
  const [expanded, setExpanded] = React.useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({
    nodes: [],
    edges: [],
  });

  /* ------------------------------------------------------------ debounced search */
  const [debouncedSearch, setDebouncedSearch] = React.useState(graphSearch);
  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(graphSearch), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [graphSearch]);

  /* ------------------------------------------------------------------------ data */
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: [
      "graph",
      projectId,
      zoom,
      domainFilter,
      serviceFilter,
      debouncedSearch,
      includeInferred,
      scenarioId,
    ],
    queryFn: () =>
      api.graph(projectId, {
        level: zoom,
        domain: domainFilter ?? undefined,
        service: serviceFilter ?? undefined,
        search: debouncedSearch || undefined,
        include_inferred: includeInferred,
        scenario: scenarioId ?? undefined,
        max_nodes: MAX_NODES,
      }),
    placeholderData: keepPreviousData,
  });

  // The filter options come from a stable level-2 read rather than the filtered result,
  // so choosing a service never removes the other services from the list you chose it in.
  const { data: facets } = useQuery({
    queryKey: ["graph-facets", projectId, scenarioId],
    queryFn: () => api.graph(projectId, { level: 2, scenario: scenarioId ?? undefined }),
    staleTime: 5 * 60_000,
  });

  const { domains, services } = React.useMemo(() => {
    const pool = [...(facets?.nodes ?? []), ...(data?.nodes ?? [])];
    const domainMap = new Map<string, string>();
    const serviceMap = new Map<string, string>();
    for (const node of pool) {
      if (node.type === "Domain") domainMap.set(node.id, node.label);
      if (node.type === "Service") {
        const slug = (node.attrs?.slug as string) ?? node.id;
        serviceMap.set(slug, node.label);
      }
    }
    const sort = (map: Map<string, string>): FilterOption[] =>
      [...map.entries()]
        .map(([value, label]) => ({ value, label }))
        .sort((a, b) => a.label.localeCompare(b.label));
    return { domains: sort(domainMap), services: sort(serviceMap) };
  }, [facets, data]);

  /* --------------------------------------------------- neighbour expansion merge */
  // A change of query means a different question; anything pulled in for the old one is
  // no longer part of the answer.
  React.useEffect(() => {
    setExpanded({ nodes: [], edges: [] });
  }, [projectId, zoom, domainFilter, serviceFilter, debouncedSearch, includeInferred, scenarioId]);

  const onExpand = React.useCallback(
    async (nodeId: string) => {
      try {
        const result = await api.neighbors(projectId, nodeId, 2, scenarioId ?? undefined);
        setExpanded((previous) => {
          const nodes = new Map(previous.nodes.map((node) => [node.id, node]));
          const edges = new Map(previous.edges.map((edge) => [edge.id, edge]));
          for (const node of result.nodes) nodes.set(node.id, node);
          for (const edge of result.edges) edges.set(edge.id, edge);
          return { nodes: [...nodes.values()], edges: [...edges.values()] };
        });
        toast("info", `Pulled in ${result.nodes.length} neighbours, two hops out.`);
      } catch (cause) {
        toast(
          "error",
          cause instanceof ApiError ? cause.message : "Could not expand that node.",
        );
      }
    },
    [projectId, scenarioId, toast],
  );

  const { nodes, edges } = React.useMemo(() => {
    const nodeMap = new Map<string, GraphNode>();
    const edgeMap = new Map<string, GraphEdge>();
    for (const node of data?.nodes ?? []) nodeMap.set(node.id, node);
    for (const edge of data?.edges ?? []) edgeMap.set(edge.id, edge);
    for (const node of expanded.nodes) if (!nodeMap.has(node.id)) nodeMap.set(node.id, node);
    for (const edge of expanded.edges) if (!edgeMap.has(edge.id)) edgeMap.set(edge.id, edge);
    return { nodes: [...nodeMap.values()], edges: [...edgeMap.values()] };
  }, [data, expanded]);

  /* ---------------------------------------------------------------- canvas verbs */
  const handleFocus = React.useCallback(() => {
    if (!selectedNodeId) return;
    canvasRef.current?.focus(selectedNodeId, 1);
    setFocused(true);
  }, [selectedNodeId]);

  const handleClearFocus = React.useCallback(() => {
    canvasRef.current?.clearFocus();
    setFocused(false);
  }, []);

  const handleReset = React.useCallback(() => {
    canvasRef.current?.reset();
    setFocused(false);
  }, []);

  const clearFilters = React.useCallback(() => {
    setGraphSearch("");
    setDomainFilter(null);
    setServiceFilter(null);
    setIncludeInferred(true);
  }, [setGraphSearch, setDomainFilter, setServiceFilter, setIncludeInferred]);

  const onSelectNode = React.useCallback((nodeId: string | null) => select(nodeId), [select]);
  const onSelectEdge = React.useCallback((edgeId: string) => selectEdge(edgeId), [selectEdge]);

  // Switching back from the list view can leave the canvas sized from before a resize.
  React.useEffect(() => {
    if (view !== "graph") return;
    const core = canvasRef.current?.core();
    if (core && !core.destroyed()) core.resize();
  }, [view]);

  React.useEffect(() => {
    if (wide) setDrawerOpen(false);
  }, [wide]);

  const getCore = React.useCallback(() => canvasRef.current?.core() ?? null, []);
  const level = ZOOM_LEVELS.find((entry) => entry.level === zoom) ?? ZOOM_LEVELS[1];
  const showHighlightBar = Boolean(
    highlight.reason || highlight.nodes.length || highlight.path.length,
  );

  const filters = (
    <GraphFilters
      search={graphSearch}
      onSearch={setGraphSearch}
      domain={domainFilter}
      onDomain={setDomainFilter}
      domains={domains}
      service={serviceFilter}
      onService={setServiceFilter}
      services={services}
      includeInferred={includeInferred}
      onIncludeInferred={setIncludeInferred}
      onClear={clearFilters}
      matched={data ? nodes.length : undefined}
      total={data?.stats?.nodes}
    />
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        icon={Compass}
        title="Galaxy"
        subtitle={
          <>
            <span className="text-[var(--color-ink-2)]">{level.name}</span> — {level.detail} Click
            a node to inspect it, double-click to pull in its neighbours.
          </>
        }
        actions={<SemanticZoom value={zoom} onChange={setZoom} />}
      />

      <div className="flex min-h-0 flex-1">
        {/* ------------------------------------------------------- filter rail */}
        <aside
          className="hidden w-[252px] shrink-0 overflow-y-auto border-r border-[var(--color-line)] lg:block"
          aria-label="Graph filters"
        >
          {filters}
        </aside>

        {/* ------------------------------------------------------------ centre */}
        <section className="relative flex min-w-0 flex-1 flex-col">
          {/* toolbar */}
          <div className="scroll-x flex h-11 shrink-0 items-center gap-2 border-b border-[var(--color-line)] px-3">
            <div role="tablist" aria-label="Graph view" className="flex shrink-0 items-center gap-1">
              <ViewTab
                active={view === "graph"}
                onClick={() => setView("graph")}
                icon={<Network size={13} aria-hidden />}
                label="Canvas"
                controls="galaxy-canvas-panel"
              />
              <ViewTab
                active={view === "list"}
                onClick={() => setView("list")}
                icon={<List size={13} aria-hidden />}
                label="List view"
                controls="galaxy-list-panel"
              />
            </div>

            <span className="h-5 w-px shrink-0 bg-[var(--color-line)]" aria-hidden />

            <LayoutPicker value={layout} onChange={setLayout} />

            <span className="h-5 w-px shrink-0 bg-[var(--color-line)]" aria-hidden />

            <CanvasControls
              onZoomIn={() => canvasRef.current?.zoomBy(1.3)}
              onZoomOut={() => canvasRef.current?.zoomBy(1 / 1.3)}
              onFit={() => canvasRef.current?.fit()}
              onReset={handleReset}
              onFocus={handleFocus}
              onClearFocus={handleClearFocus}
              focusEnabled={Boolean(selectedNodeId)}
              focused={focused}
            />

            <div className="ml-auto flex shrink-0 items-center gap-2 pl-2">
              {isFetching && (
                <span
                  className="whitespace-nowrap text-[11.5px] text-[var(--color-dim)]"
                  role="status"
                >
                  Updating…
                </span>
              )}
              <Badge tone="neutral" className="whitespace-nowrap">
                <span className="numeral">{nodes.length}</span>&nbsp;nodes ·&nbsp;
                <span className="numeral">{edges.length}</span>&nbsp;edges
              </Badge>

              <Button
                variant="ghost"
                size="sm"
                className="lg:hidden"
                onClick={() => setFiltersOpen(true)}
              >
                <SlidersHorizontal size={13} aria-hidden />
                Filters
              </Button>

              {!wide && (
                <Tooltip label="Show the inspector">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setDrawerOpen(true)}
                    aria-label="Show the inspector"
                  >
                    <PanelRightOpen size={13} aria-hidden />
                    Inspector
                  </Button>
                </Tooltip>
              )}
            </div>
          </div>

          {/* highlight bar */}
          {showHighlightBar && (
            <div className="flex shrink-0 items-start gap-2 border-b border-[color-mix(in_oklab,var(--color-accent)_34%,transparent)] bg-[color-mix(in_oklab,var(--color-accent)_10%,transparent)] px-3 py-2">
              <Badge tone="accent" className="mt-[1px] shrink-0">
                Highlighted
              </Badge>
              <p className="min-w-0 flex-1 text-[12.5px] leading-snug text-[var(--color-ink-2)]">
                {highlight.reason || "A path is highlighted on the canvas."}
                {highlight.path.length > 0 && (
                  <span className="ml-1 text-[var(--color-dim)]">
                    <span className="numeral">{highlight.path.length}</span> hops.
                  </span>
                )}
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={clearHighlight}
                aria-label="Clear the highlight"
              >
                <X size={13} aria-hidden />
                Clear
              </Button>
            </div>
          )}

          {/* truncation bar */}
          {data?.truncated && (
            <div
              role="status"
              className="flex shrink-0 items-start gap-2 border-b border-[color-mix(in_oklab,var(--color-degraded)_38%,transparent)] bg-[color-mix(in_oklab,var(--color-degraded)_12%,transparent)] px-3 py-2"
            >
              <Badge tone="degraded" className="mt-[1px] shrink-0">
                Truncated
              </Badge>
              <p className="min-w-0 flex-1 text-[12.5px] leading-snug text-[var(--color-ink-2)]">
                {data.truncation_reason || "Not every matching node is being drawn."} Narrow the
                view with a domain, a service or a search to see the rest.
              </p>
            </div>
          )}

          {/* canvas + panels */}
          <div className="relative min-h-0 flex-1">
            <div
              id="galaxy-canvas-panel"
              role="tabpanel"
              aria-label="Graph canvas"
              className={cx(
                "absolute inset-0 transition-opacity duration-150",
                view === "graph" ? "opacity-100" : "pointer-events-none opacity-0",
              )}
              aria-hidden={view !== "graph"}
            >
              <GraphCanvas
                ref={canvasRef}
                nodes={nodes}
                edges={edges}
                selectedId={selectedNodeId}
                highlightNodes={highlight.nodes}
                highlightEdges={highlight.edges}
                pathNodes={highlight.path}
                layout={layout}
                onSelectNode={onSelectNode}
                onSelectEdge={onSelectEdge}
                onExpand={onExpand}
                className="absolute inset-0 h-full w-full"
              />
            </div>

            {view === "graph" && (
              <>
                <GraphLegend className="absolute bottom-3 left-3 z-10" />
                <Minimap
                  getCore={getCore}
                  version={nodes.length + edges.length}
                  className="absolute bottom-3 right-3 z-10"
                />
              </>
            )}

            {/* The keyboard-navigable equivalent. Always one click away, never a fallback. */}
            <div
              id="galaxy-list-panel"
              role="tabpanel"
              aria-label="Node list"
              hidden={view !== "list"}
              className="absolute inset-0 z-20 overflow-y-auto bg-[var(--color-base)]"
            >
              <div className="border-b border-[var(--color-line)] px-3 py-2">
                <p className="text-[12px] text-[var(--color-muted)]">
                  The same <span className="numeral">{nodes.length}</span> nodes as the canvas,
                  as a list. Tab to move through them, Enter to inspect.
                </p>
              </div>
              <GraphNodeList
                nodes={nodes}
                selectedId={selectedNodeId}
                onSelect={(nodeId) => select(nodeId)}
                emptyLabel="No nodes match the current filters."
              />
            </div>

            {/* states */}
            {isLoading && (
              <div className="absolute inset-0 z-30 flex items-center justify-center bg-[var(--color-base)]">
                <div className="w-[320px] space-y-3" role="status" aria-label="Loading the graph">
                  <Skeleton className="h-4 w-1/2" />
                  <Skeleton className="h-[180px] w-full" />
                  <Skeleton className="h-4 w-2/3" />
                  <span className="sr-only">Loading the graph</span>
                </div>
              </div>
            )}

            {error && (
              <div className="absolute inset-0 z-30 flex items-center justify-center bg-[var(--color-base)] p-6">
                <div className="w-full max-w-lg">
                  <ErrorState
                    title="Could not load the graph"
                    detail={
                      error instanceof ApiError
                        ? error.message
                        : "The graph request failed. The backend may not be running on port 8099."
                    }
                    hint={error instanceof ApiError ? error.hint : undefined}
                    correlationId={error instanceof ApiError ? error.correlationId : undefined}
                    onRetry={() => void refetch()}
                  />
                </div>
              </div>
            )}

            {!isLoading && !error && nodes.length === 0 && (
              <div className="absolute inset-0 z-30 flex items-center justify-center bg-[var(--color-base)]">
                <EmptyState
                  icon={<Compass size={22} aria-hidden />}
                  title="Nothing matches these filters"
                  body="No node at this zoom level matches the domain, service and search you have set. Widen one of them, or drop to a deeper level."
                  action={
                    <Button variant="secondary" size="sm" onClick={clearFilters}>
                      Clear filters
                    </Button>
                  }
                />
              </div>
            )}
          </div>
        </section>

        {/* ---------------------------------------------------------- inspector */}
        {wide && (
          <InspectorRail>
            <Inspector projectId={projectId} />
          </InspectorRail>
        )}
      </div>

      {/* Below 1100px the inspector is a drawer, so the canvas keeps the screen. */}
      {!wide && drawerOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50"
            onClick={() => setDrawerOpen(false)}
            aria-hidden
          />
          <aside
            className="fixed bottom-0 right-0 top-12 z-50 w-[330px] overflow-y-auto border-l border-[var(--color-line)] bg-[var(--color-surface)] shadow-[var(--shadow-lift)]"
            aria-label="Inspector"
            onKeyDown={(event) => {
              if (event.key === "Escape") setDrawerOpen(false);
            }}
          >
            <div className="flex items-center justify-between border-b border-[var(--color-line)] px-3 py-2">
              <span className="label-eyebrow">Inspector</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close the inspector"
              >
                <X size={14} />
              </Button>
            </div>
            <Inspector projectId={projectId} />
          </aside>
        </>
      )}

      <Dialog
        open={filtersOpen}
        onOpenChange={setFiltersOpen}
        title="Filters"
        description="These are the same controls as the rail on a wider screen."
      >
        {filters}
      </Dialog>
    </div>
  );
}

function ViewTab({
  active,
  onClick,
  icon,
  label,
  controls,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  controls: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      onClick={onClick}
      className={cx(
        "flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[var(--radius-sm)] px-2.5 py-1.5",
        "text-[12px] font-medium transition-colors duration-150",
        active
          ? "bg-[var(--color-surface-3)] text-[var(--color-ink)]"
          : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

/**
 * Defaults to the wide layout so the server render and the first client render agree;
 * the real value lands on the first effect.
 */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = React.useState(true);
  React.useEffect(() => {
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}
