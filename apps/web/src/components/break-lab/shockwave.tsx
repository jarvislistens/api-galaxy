"use client";

/**
 * The blast radius: four numbers and the table that explains them.
 *
 * Status is never carried by colour alone — every cell has an icon and the word as well,
 * because a printed report, a colour-blind reader and a screen reader all need the same
 * information the colour is giving.
 *
 * `normaliseItem` is a tolerant reader. The backend now emits one shape for both
 * `impact.items[]` and `shockwave[]` (`node_label`/`node_type`), but it briefly emitted
 * `label`/`type` for the latter — which type-checked and rendered `undefined`. Accepting
 * either costs three lines and means this table cannot be broken that way again.
 */

import { motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  ArrowUpDown,
  CheckCircle2,
  ChevronRight,
  HelpCircle,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { Badge, EmptyState, cx } from "@/components/ui/primitives";
import { STATUS_COLOUR } from "@/components/graph/graph-style";
import type { ImpactItem, ImpactStatus } from "@/lib/types";

export interface Shockwave {
  node_id: string;
  label: string;
  type: string;
  status: ImpactStatus;
  distance: number;
  reason: string;
  chain: string[];
  chain_labels: string[];
  via: string[];
}

export function normaliseItem(raw: ImpactItem | Record<string, any>): Shockwave {
  const item = raw as Record<string, any>;
  return {
    node_id: item.node_id,
    label: item.label ?? item.node_label ?? item.node_id,
    type: item.type ?? item.node_type ?? "",
    status: item.status,
    distance: item.distance ?? 0,
    reason: item.reason ?? "",
    chain: item.chain ?? [],
    chain_labels: item.chain_labels ?? [],
    via: item.via ?? [],
  };
}

/**
 * Relationships that carry a contract the far end consumes, as opposed to ones that
 * carry meaning. Mirrors `CONTRACT_EDGES` in the backend's graph engine — the backend
 * decides severity with it; this only decides how the hop is coloured.
 */
export const CONTRACT_RELATIONS = new Set([
  "CONTAINS",
  "EXPOSES",
  "USES_REQUEST",
  "RETURNS",
  "REFERENCES",
  "DEPENDS_ON",
  "CALLS_OR_PRECEDES",
  "PART_OF_JOURNEY",
]);

/** "ALIAS_OF" → "alias of". The relationship type, in words the reader already knows. */
export function relationWords(edgeType: string): string {
  return edgeType.replace(/_/g, " ").toLowerCase();
}

/**
 * Render the route as `Customer —contains→ customer_id`, so the chain shows *what kind*
 * of relationship each hop was. A chain of bare names cannot distinguish a contract the
 * far end consumes from a suggestion that it means the same thing.
 */
export function describeRoute(item: Shockwave): string {
  if (!item.chain_labels.length) return "";
  return item.chain_labels.reduce((text, label, index) => {
    if (index === 0) return label;
    const relation = item.via[index - 1];
    return `${text} —${relation ? relationWords(relation) : "→"}→ ${label}`;
  }, "");
}

export const STATUS_META: Record<
  ImpactStatus,
  { word: string; icon: typeof XCircle; detail: string; tone: "broken" | "degraded" | "possible" | "ok" }
> = {
  broken: {
    word: "Broken",
    icon: XCircle,
    detail: "Cannot work without a code change",
    tone: "broken",
  },
  degraded: {
    word: "Degraded",
    icon: AlertTriangle,
    // Two hops along a contract, or any hop through a meaning-carrying link such as an
    // alias. Both leave the shape intact and move what it means.
    detail: "Still type-checks, but the meaning moved",
    tone: "degraded",
  },
  potentially_affected: {
    word: "Potentially affected",
    icon: HelpCircle,
    // Was "reached only through an inferred relationship", which stopped being the whole
    // story once severity became route-aware: distance alone puts things here too.
    detail: "Further away, or reached through a suggested link",
    tone: "possible",
  },
  unaffected: {
    word: "Unaffected",
    icon: CheckCircle2,
    detail: "Nothing in the graph connects it to this change",
    tone: "ok",
  },
};

const ORDER: ImpactStatus[] = ["broken", "degraded", "potentially_affected", "unaffected"];

/* ------------------------------------------------------------------- counts */

export function ImpactCounts({
  counts,
  pulseKey,
}: {
  counts: Record<string, number>;
  /** Changes whenever a new change lands, so the numbers can acknowledge it once. */
  pulseKey: string;
}) {
  const reduce = useReducedMotion();
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-line)] xl:grid-cols-4">
      {ORDER.map((status) => {
        const meta = STATUS_META[status];
        const Icon = meta.icon;
        const value = counts[status] ?? 0;
        return (
          <div key={status} className="bg-[var(--color-surface)] p-4">
            <div className="flex items-center gap-1.5">
              <Icon
                size={13}
                aria-hidden
                style={{
                  color:
                    status === "unaffected"
                      ? "var(--color-ok)"
                      : STATUS_COLOUR[status] || "var(--color-muted)",
                }}
              />
              <span className="text-[12px] font-medium text-[var(--color-ink-2)]">{meta.word}</span>
            </div>
            <motion.div
              key={`${pulseKey}-${status}-${value}`}
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              className="numeral mt-1.5 text-[30px] font-semibold leading-none"
              style={{
                color:
                  status === "unaffected"
                    ? "var(--color-ink)"
                    : STATUS_COLOUR[status] || "var(--color-ink)",
              }}
            >
              {value}
            </motion.div>
            <p className="mt-1.5 text-[11.5px] leading-snug text-[var(--color-dim)]">
              {meta.detail}
            </p>
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------- table */

type SortKey = "status" | "distance" | "type" | "label";

const STATUS_RANK: Record<string, number> = {
  broken: 0,
  degraded: 1,
  potentially_affected: 2,
  unaffected: 3,
};

export function ShockwaveTable({
  items,
  onSelect,
  selectedId,
}: {
  items: Shockwave[];
  onSelect: (nodeId: string) => void;
  selectedId?: string | null;
}) {
  const [sort, setSort] = React.useState<{ key: SortKey; asc: boolean }>({
    key: "status",
    asc: true,
  });
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  const [filter, setFilter] = React.useState<ImpactStatus | "all">("all");

  const visible = React.useMemo(() => {
    const filtered = filter === "all" ? items : items.filter((item) => item.status === filter);
    const direction = sort.asc ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sort.key === "status") {
        const diff = (STATUS_RANK[a.status] ?? 9) - (STATUS_RANK[b.status] ?? 9);
        return (diff || a.distance - b.distance) * direction;
      }
      if (sort.key === "distance") return (a.distance - b.distance) * direction;
      if (sort.key === "type") return a.type.localeCompare(b.type) * direction;
      return a.label.localeCompare(b.label) * direction;
    });
  }, [items, sort, filter]);

  const toggleSort = (key: SortKey) =>
    setSort((current) => ({ key, asc: current.key === key ? !current.asc : true }));

  const toggleRow = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (!items.length) {
    return (
      <EmptyState
        title="Nothing is affected yet"
        body="Add a change above and the nodes it reaches will be listed here, each with the dependency chain that explains why."
      />
    );
  }

  const header = (key: SortKey, label: string, className?: string) => (
    <th scope="col" className={cx("px-3 py-2 text-left font-medium", className)}
        aria-sort={sort.key === key ? (sort.asc ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() => toggleSort(key)}
        className="flex items-center gap-1 text-[11.5px] uppercase tracking-wide text-[var(--color-dim)] transition-colors hover:text-[var(--color-ink)]"
      >
        {label}
        <ArrowUpDown size={11} aria-hidden className={sort.key === key ? "opacity-100" : "opacity-40"} />
      </button>
    </th>
  );

  return (
    <div>
      <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
        <span className="label-eyebrow mr-1">Show</span>
        {(["all", ...ORDER] as const).map((option) => {
          const active = filter === option;
          const count =
            option === "all" ? items.length : items.filter((item) => item.status === option).length;
          return (
            <button
              key={option}
              type="button"
              onClick={() => setFilter(option as ImpactStatus | "all")}
              aria-pressed={active}
              className={cx(
                "rounded-full border px-2.5 py-[3px] text-[11.5px] transition-colors",
                active
                  ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_16%,transparent)] text-[var(--color-ink)]"
                  : "border-[var(--color-line-strong)] text-[var(--color-muted)] hover:text-[var(--color-ink)]",
              )}
            >
              {option === "all" ? "Everything" : STATUS_META[option as ImpactStatus].word}{" "}
              <span className="numeral text-[var(--color-dim)]">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="scroll-x max-h-[520px] overflow-y-auto rounded-[var(--radius-md)] border border-[var(--color-line)]">
        <table className="w-full border-collapse text-[12.5px]">
          <caption className="sr-only">
            Nodes reached by this scenario, with status, distance from the change and the
            dependency chain.
          </caption>
          <thead className="sticky top-0 z-10 bg-[var(--color-surface-2)]">
            <tr className="border-b border-[var(--color-line)]">
              <th scope="col" className="w-8 px-2 py-2">
                <span className="sr-only">Expand the dependency chain</span>
              </th>
              {header("status", "Status", "w-[168px]")}
              {header("distance", "Hops", "w-[72px]")}
              {header("type", "Type", "w-[120px]")}
              {header("label", "Node")}
              <th scope="col" className="px-3 py-2 text-left text-[11.5px] uppercase tracking-wide text-[var(--color-dim)]">
                Why
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => {
              const meta = STATUS_META[item.status] ?? STATUS_META.potentially_affected;
              const Icon = meta.icon;
              const open = expanded.has(item.node_id);
              const selected = selectedId === item.node_id;
              return (
                <React.Fragment key={item.node_id}>
                  <tr
                    className={cx(
                      "border-b border-[var(--color-line)] transition-colors",
                      selected ? "bg-[var(--color-surface-3)]" : "hover:bg-[var(--color-surface-2)]",
                    )}
                  >
                    <td className="px-2 py-1.5 align-top">
                      <button
                        type="button"
                        onClick={() => toggleRow(item.node_id)}
                        aria-expanded={open}
                        aria-label={`${open ? "Hide" : "Show"} the dependency chain for ${item.label}`}
                        className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-dim)] transition-colors hover:text-[var(--color-ink)]"
                      >
                        <ChevronRight
                          size={13}
                          className={cx("transition-transform duration-150", open && "rotate-90")}
                          aria-hidden
                        />
                      </button>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <span className="flex items-center gap-1.5">
                        <Icon
                          size={12}
                          aria-hidden
                          style={{
                            color:
                              item.status === "unaffected"
                                ? "var(--color-ok)"
                                : STATUS_COLOUR[item.status] || "var(--color-muted)",
                          }}
                        />
                        <span className="text-[var(--color-ink-2)]">{meta.word}</span>
                      </span>
                    </td>
                    <td className="numeral px-3 py-2 align-top text-[var(--color-ink-2)]">
                      {item.distance}
                    </td>
                    <td className="px-3 py-2 align-top text-[var(--color-muted)]">{item.type}</td>
                    <td className="px-3 py-2 align-top">
                      <button
                        type="button"
                        onClick={() => onSelect(item.node_id)}
                        className="max-w-[320px] truncate text-left text-[var(--color-ink)] underline-offset-2 hover:underline"
                        title={item.node_id}
                      >
                        {item.label}
                      </button>
                    </td>
                    <td className="px-3 py-2 align-top text-[var(--color-muted)]">{item.reason}</td>
                  </tr>
                  {open && (
                    <tr className="border-b border-[var(--color-line)] bg-[var(--color-base)]">
                      <td />
                      <td colSpan={5} className="px-3 py-2.5">
                        <p className="label-eyebrow mb-1">How the change reaches this</p>
                        <p className="mono scroll-x whitespace-nowrap text-[11.5px] text-[var(--color-ink-2)]">
                          {item.chain_labels.length
                            ? describeRoute(item)
                            : "This node is the change itself."}
                        </p>
                        {item.via.length > 0 && (
                          <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
                            {item.via.map((relation, index) => (
                              <Badge
                                key={`${relation}-${index}`}
                                tone={CONTRACT_RELATIONS.has(relation) ? "fact" : "inferred"}
                              >
                                {relationWords(relation)}
                              </Badge>
                            ))}
                            <span className="text-[11px] text-[var(--color-dim)]">
                              {item.via.every((relation) => CONTRACT_RELATIONS.has(relation))
                                ? "every hop is a contract it consumes"
                                : "at least one hop carries meaning, not a contract"}
                            </span>
                          </p>
                        )}
                        <p className="mono mt-1.5 break-all text-[11px] text-[var(--color-dim)]">
                          {item.node_id}
                        </p>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-[12.5px] text-[var(--color-dim)]">
                  Nothing in this category.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-2 flex items-center gap-2 text-[11.5px] text-[var(--color-dim)]">
        <Badge tone="neutral">{visible.length} shown</Badge>
        Selecting a node opens it in the inspector on the right.
      </p>
    </div>
  );
}
