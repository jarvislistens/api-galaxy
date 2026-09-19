"use client";

/**
 * Everything you can do to the view, as opposed to the data.
 *
 * Semantic zoom is the important one. Levels are named in words — "Business
 * capabilities", "Fields" — because "level 3" tells a reader nothing about what they are
 * about to be shown. The number is kept alongside only as a shorthand for people who
 * have learned it.
 */

import {
  Crosshair,
  Focus,
  Layers,
  Maximize2,
  RotateCcw,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import * as React from "react";
import {
  Button,
  Field,
  Input,
  InfoNote,
  Select,
  Switch,
  Tooltip,
  cx,
} from "@/components/ui/primitives";
import type { LayoutName } from "@/components/graph/graph-canvas";
import type { ZoomLevel } from "@/lib/store";

export const ZOOM_LEVELS: {
  level: ZoomLevel;
  name: string;
  short: string;
  detail: string;
}[] = [
  {
    level: 1,
    name: "Business capabilities",
    short: "Capabilities",
    detail: "Domains and what the estate can do. No technology.",
  },
  {
    level: 2,
    name: "Services and journeys",
    short: "Services",
    detail: "The services, the business entities and the flows across them.",
  },
  {
    level: 3,
    name: "Endpoints and schemas",
    short: "Endpoints",
    detail: "Operations, endpoints, schemas, security and findings.",
  },
  {
    level: 4,
    name: "Fields",
    short: "Fields",
    detail: "Every leaf field. Dense on purpose — filter or search first.",
  },
];

/** The semantic zoom control. A radiogroup, because exactly one level is in force. */
export function SemanticZoom({
  value,
  onChange,
  className,
}: {
  value: ZoomLevel;
  onChange: (level: ZoomLevel) => void;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Semantic zoom level"
      className={cx(
        "flex items-center gap-1 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface)] p-1",
        className,
      )}
    >
      {ZOOM_LEVELS.map((entry) => {
        const active = entry.level === value;
        return (
          <Tooltip key={entry.level} label={entry.detail}>
            <button
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(entry.level)}
              className={cx(
                "flex items-center gap-1.5 rounded-[var(--radius-xs)] px-2.5 py-1.5 text-[12.5px] font-medium",
                "transition-colors duration-150",
                active
                  ? "bg-[var(--color-surface-3)] text-[var(--color-ink)]"
                  : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
              )}
            >
              <span className="numeral text-[11px] text-[var(--color-dim)]">{entry.level}</span>
              <span className="hidden whitespace-nowrap xl:inline">{entry.name}</span>
              <span className="whitespace-nowrap xl:hidden">{entry.short}</span>
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}

export interface FilterOption {
  value: string;
  label: string;
}

/** Search and the two data filters. Used in the rail and, at narrow widths, in a dialog. */
export function GraphFilters({
  search,
  onSearch,
  domain,
  onDomain,
  domains,
  service,
  onService,
  services,
  includeInferred,
  onIncludeInferred,
  onClear,
  matched,
  total,
  className,
}: {
  search: string;
  onSearch: (value: string) => void;
  domain: string | null;
  onDomain: (value: string | null) => void;
  domains: FilterOption[];
  service: string | null;
  onService: (value: string | null) => void;
  services: FilterOption[];
  includeInferred: boolean;
  onIncludeInferred: (value: boolean) => void;
  onClear: () => void;
  matched?: number;
  total?: number;
  className?: string;
}) {
  const dirty = Boolean(search || domain || service) || !includeInferred;

  return (
    <div className={cx("space-y-4 p-3.5", className)}>
      <div>
        <p className="label-eyebrow mb-2">Find</p>
        <div className="relative">
          <Search
            size={13}
            aria-hidden
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-dim)]"
          />
          <Input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search nodes…"
            aria-label="Search the graph"
            className="pl-8 pr-8"
          />
          {search && (
            <button
              type="button"
              onClick={() => onSearch("")}
              aria-label="Clear the search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-dim)] transition-colors hover:text-[var(--color-ink)]"
            >
              <X size={13} aria-hidden />
            </button>
          )}
        </div>
        <p className="mt-1.5 text-[11.5px] text-[var(--color-dim)]">
          Matches labels, descriptions and field names.
        </p>
      </div>

      <div className="space-y-3">
        <p className="label-eyebrow">Filter</p>

        <Field label="Business domain">
          <Select
            value={domain ?? ""}
            onChange={(event) => onDomain(event.target.value || null)}
          >
            <option value="">All domains</option>
            {domains.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Service">
          <Select
            value={service ?? ""}
            onChange={(event) => onService(event.target.value || null)}
          >
            <option value="">All services</option>
            {services.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <div className="space-y-2 border-t border-[var(--color-line)] pt-3.5">
        <Switch
          checked={includeInferred}
          onCheckedChange={onIncludeInferred}
          label="Show inferred relationships"
          description="Suggestions rather than statements. Drawn dashed."
        />
      </div>

      {(matched !== undefined || dirty) && (
        <div className="space-y-2 border-t border-[var(--color-line)] pt-3.5">
          {matched !== undefined && (
            <p className="text-[12px] text-[var(--color-muted)]">
              Showing <span className="numeral text-[var(--color-ink-2)]">{matched}</span>
              {total !== undefined && (
                <>
                  {" of "}
                  <span className="numeral text-[var(--color-ink-2)]">{total}</span>
                </>
              )}{" "}
              nodes at this level.
            </p>
          )}
          {dirty && (
            <Button variant="ghost" size="sm" onClick={onClear} className="w-full justify-start">
              <RotateCcw size={13} aria-hidden />
              Clear filters
            </Button>
          )}
        </div>
      )}

      <div className="border-t border-[var(--color-line)] pt-3.5">
        <InfoNote>
          Double-click any node on the canvas to pull in its neighbours two hops out.
        </InfoNote>
      </div>
    </div>
  );
}

/** Layout choice. Kept as a labelled select rather than icons — the names are the point. */
export function LayoutPicker({
  value,
  onChange,
}: {
  value: LayoutName;
  onChange: (value: LayoutName) => void;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1.5 text-[12px] text-[var(--color-muted)]">
      <Layers size={13} aria-hidden className="shrink-0" />
      <Select
        value={value}
        onChange={(event) => onChange(event.target.value as LayoutName)}
        aria-label="Graph layout"
        className="h-8 w-[104px] shrink-0"
      >
        <option value="force">Force</option>
        <option value="hierarchy">Hierarchy</option>
        <option value="circle">Circle</option>
        <option value="grid">Grid</option>
      </Select>
    </div>
  );
}

/** Pan, zoom, fit, reset, focus. Icon-only, so every one carries a label. */
export function CanvasControls({
  onZoomIn,
  onZoomOut,
  onFit,
  onReset,
  onFocus,
  onClearFocus,
  focusEnabled,
  focused,
}: {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onReset: () => void;
  onFocus: () => void;
  onClearFocus: () => void;
  focusEnabled: boolean;
  focused: boolean;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <Tooltip label="Zoom in">
        <Button variant="ghost" size="sm" onClick={onZoomIn} aria-label="Zoom in">
          <ZoomIn size={14} />
        </Button>
      </Tooltip>
      <Tooltip label="Zoom out">
        <Button variant="ghost" size="sm" onClick={onZoomOut} aria-label="Zoom out">
          <ZoomOut size={14} />
        </Button>
      </Tooltip>
      <Tooltip label="Fit everything on screen">
        <Button variant="ghost" size="sm" onClick={onFit} aria-label="Fit the graph on screen">
          <Maximize2 size={14} />
        </Button>
      </Tooltip>
      <Tooltip label="Reset the view and clear highlighting">
        <Button variant="ghost" size="sm" onClick={onReset} aria-label="Reset the view">
          <RotateCcw size={14} />
        </Button>
      </Tooltip>

      <span className="mx-1 h-5 w-px bg-[var(--color-line)]" aria-hidden />

      <Tooltip label="Focus on the selected node and its immediate neighbours">
        <Button
          variant={focused ? "primary" : "ghost"}
          size="sm"
          onClick={onFocus}
          disabled={!focusEnabled}
          aria-label="Focus on the selected node"
        >
          <Focus size={14} />
          <span className="hidden @[860px]:inline">Focus</span>
        </Button>
      </Tooltip>
      <Tooltip label="Show the whole graph again">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClearFocus}
          disabled={!focused}
          aria-label="Clear focus"
        >
          <Crosshair size={14} />
        </Button>
      </Tooltip>
    </div>
  );
}
