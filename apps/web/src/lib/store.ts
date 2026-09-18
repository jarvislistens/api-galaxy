/**
 * Transient workspace state.
 *
 * Server data lives in TanStack Query. This store holds only what the *workspace* needs
 * to remember across panels: what is selected, what is highlighted, which scenario is
 * active, and the undo stack for user edits. None of it is persisted, because none of it
 * is a fact about the project.
 */

import { create } from "zustand";

export type ZoomLevel = 1 | 2 | 3 | 4;

export interface Highlight {
  nodes: string[];
  edges: string[];
  path: string[];
  reason: string;
}

export interface UndoEntry {
  label: string;
  undo: () => Promise<void> | void;
  redo: () => Promise<void> | void;
}

interface WorkspaceState {
  projectId: string | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  highlight: Highlight;
  zoom: ZoomLevel;
  domainFilter: string | null;
  serviceFilter: string | null;
  includeInferred: boolean;
  graphSearch: string;
  activeScenarioId: string | null;
  commandOpen: boolean;
  inspectorOpen: boolean;
  missionId: string | null;
  layout: "force" | "hierarchy" | "circle" | "grid";
  toasts: { id: string; tone: "info" | "success" | "warning" | "error"; text: string }[];
  undoStack: UndoEntry[];
  redoStack: UndoEntry[];

  setProject: (id: string | null) => void;
  select: (nodeId: string | null) => void;
  selectEdge: (edgeId: string | null) => void;
  setHighlight: (highlight: Partial<Highlight>) => void;
  clearHighlight: () => void;
  setZoom: (zoom: ZoomLevel) => void;
  setDomainFilter: (domain: string | null) => void;
  setServiceFilter: (service: string | null) => void;
  setIncludeInferred: (value: boolean) => void;
  setGraphSearch: (value: string) => void;
  setScenario: (id: string | null) => void;
  setCommandOpen: (open: boolean) => void;
  setInspectorOpen: (open: boolean) => void;
  setMission: (id: string | null) => void;
  setLayout: (layout: WorkspaceState["layout"]) => void;
  toast: (tone: "info" | "success" | "warning" | "error", text: string) => void;
  dismissToast: (id: string) => void;
  pushUndo: (entry: UndoEntry) => void;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  reset: () => void;
}

const EMPTY_HIGHLIGHT: Highlight = { nodes: [], edges: [], path: [], reason: "" };

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  projectId: null,
  selectedNodeId: null,
  selectedEdgeId: null,
  highlight: EMPTY_HIGHLIGHT,
  zoom: 2,
  domainFilter: null,
  serviceFilter: null,
  includeInferred: true,
  graphSearch: "",
  activeScenarioId: null,
  commandOpen: false,
  inspectorOpen: true,
  missionId: null,
  layout: "force",
  toasts: [],
  undoStack: [],
  redoStack: [],

  setProject: (id) => set({ projectId: id, selectedNodeId: null, highlight: EMPTY_HIGHLIGHT }),
  select: (nodeId) => set({ selectedNodeId: nodeId, selectedEdgeId: null, inspectorOpen: true }),
  selectEdge: (edgeId) => set({ selectedEdgeId: edgeId, selectedNodeId: null, inspectorOpen: true }),
  setHighlight: (highlight) =>
    set((state) => ({ highlight: { ...state.highlight, ...highlight } })),
  clearHighlight: () => set({ highlight: EMPTY_HIGHLIGHT }),
  setZoom: (zoom) => set({ zoom }),
  setDomainFilter: (domainFilter) => set({ domainFilter }),
  setServiceFilter: (serviceFilter) => set({ serviceFilter }),
  setIncludeInferred: (includeInferred) => set({ includeInferred }),
  setGraphSearch: (graphSearch) => set({ graphSearch }),
  setScenario: (activeScenarioId) => set({ activeScenarioId }),
  setCommandOpen: (commandOpen) => set({ commandOpen }),
  setInspectorOpen: (inspectorOpen) => set({ inspectorOpen }),
  setMission: (missionId) => set({ missionId }),
  setLayout: (layout) => set({ layout }),

  toast: (tone, text) =>
    set((state) => ({
      toasts: [...state.toasts, { id: `${Date.now()}-${Math.random()}`, tone, text }].slice(-4),
    })),
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  // Undo is a stack of inverse operations rather than a graph snapshot: the graph can be
  // thousands of nodes, and every user edit here already knows how to reverse itself.
  pushUndo: (entry) =>
    set((state) => ({ undoStack: [...state.undoStack, entry].slice(-40), redoStack: [] })),
  undo: async () => {
    const { undoStack } = get();
    const entry = undoStack[undoStack.length - 1];
    if (!entry) return;
    set({ undoStack: undoStack.slice(0, -1) });
    await entry.undo();
    set((state) => ({ redoStack: [...state.redoStack, entry] }));
  },
  redo: async () => {
    const { redoStack } = get();
    const entry = redoStack[redoStack.length - 1];
    if (!entry) return;
    set({ redoStack: redoStack.slice(0, -1) });
    await entry.redo();
    set((state) => ({ undoStack: [...state.undoStack, entry] }));
  },

  reset: () =>
    set({
      selectedNodeId: null,
      selectedEdgeId: null,
      highlight: EMPTY_HIGHLIGHT,
      domainFilter: null,
      serviceFilter: null,
      graphSearch: "",
      activeScenarioId: null,
      undoStack: [],
      redoStack: [],
    }),
}));
