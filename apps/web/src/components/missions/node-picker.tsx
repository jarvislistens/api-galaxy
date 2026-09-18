"use client";

/**
 * Pick a real node by searching the real graph.
 *
 * Missions never get their own simplified catalogue: the picker queries the same search
 * endpoint the command palette uses, and shows the same identifiers, so an answer here is
 * an answer about the actual estate.
 */

import { useQuery } from "@tanstack/react-query";
import { Check, Search, X } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Button,
  ErrorState,
  Input,
  LoadingBlock,
  cx,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";

interface SearchHit {
  id: string;
  label: string;
  type: string;
  description?: string;
  service?: string | null;
  is_fact?: boolean;
}

export function NodePicker({
  projectId,
  multiple,
  value,
  onChange,
  onInspect,
}: {
  projectId: string;
  multiple?: boolean;
  value: string[];
  onChange: (ids: string[]) => void;
  onInspect?: (id: string) => void;
}) {
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 220);
    return () => window.clearTimeout(timer);
  }, [query]);

  const results = useQuery({
    queryKey: ["graph-search", projectId, debounced],
    queryFn: () => api.search(projectId, debounced),
    enabled: debounced.length >= 2,
  });

  const hits: SearchHit[] = results.data?.results ?? [];
  const chosen = new Set(value);

  const toggle = (id: string) => {
    if (multiple) {
      onChange(chosen.has(id) ? value.filter((item) => item !== id) : [...value, id]);
    } else {
      onChange(chosen.has(id) ? [] : [id]);
    }
  };

  return (
    <div className="space-y-2.5">
      <div className="relative">
        <Search
          size={13}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-dim)]"
          aria-hidden
        />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={multiple ? "Search for the nodes…" : "Search for the node…"}
          aria-label={multiple ? "Search for nodes to select" : "Search for a node to select"}
          className="pl-8"
        />
      </div>

      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Selected nodes">
          {value.map((id) => (
            <li key={id}>
              <span className="mono flex items-center gap-1.5 rounded-full border border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_14%,transparent)] py-1 pl-2.5 pr-1 text-[11px] text-[var(--color-ink)]">
                {id}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 px-1"
                  aria-label={`Remove ${id} from the answer`}
                  onClick={() => onChange(value.filter((item) => item !== id))}
                >
                  <X size={11} aria-hidden />
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="max-h-[240px] overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--color-line)]">
        {debounced.length < 2 ? (
          <p className="px-3 py-3 text-[12px] text-[var(--color-dim)]">
            Type at least two characters. Search covers every node in the graph —
            operations, schemas, fields, services and entities.
          </p>
        ) : results.isLoading ? (
          <div className="p-3">
            <LoadingBlock label="Searching the graph" rows={3} />
          </div>
        ) : results.error ? (
          <div className="p-3">
            <ErrorState
              detail={(results.error as ApiError).message}
              correlationId={(results.error as ApiError).correlationId}
              onRetry={() => void results.refetch()}
            />
          </div>
        ) : hits.length === 0 ? (
          <p className="px-3 py-3 text-[12px] text-[var(--color-dim)]">
            Nothing in the graph matches “{debounced}”.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--color-line)]">
            {hits.map((hit) => {
              const picked = chosen.has(hit.id);
              return (
                <li key={hit.id} className="flex items-start gap-1">
                  <button
                    onClick={() => toggle(hit.id)}
                    aria-pressed={picked}
                    className={cx(
                      "flex min-w-0 flex-1 items-start gap-2 px-3 py-2 text-left transition-colors duration-150",
                      picked
                        ? "bg-[color-mix(in_oklab,var(--color-accent)_12%,transparent)]"
                        : "hover:bg-[var(--color-surface-2)]",
                    )}
                  >
                    <span
                      className={cx(
                        "mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border",
                        picked
                          ? "border-[var(--color-accent)] bg-[var(--color-accent)]"
                          : "border-[var(--color-line-strong)]",
                      )}
                      aria-hidden
                    >
                      {picked && <Check size={10} className="text-[#0a0c10]" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[12.5px] text-[var(--color-ink)]">{hit.label}</span>
                        <Badge tone="neutral">{hit.type}</Badge>
                        {hit.is_fact === false && <Badge tone="inferred">inferred</Badge>}
                        {hit.service && (
                          <span className="text-[11px] text-[var(--color-dim)]">{hit.service}</span>
                        )}
                      </span>
                      <span className="mono mt-0.5 block break-all text-[10.5px] text-[var(--color-dim)]">
                        {hit.id}
                      </span>
                    </span>
                  </button>
                  {onInspect && (
                    <Button
                      variant="quiet"
                      size="sm"
                      className="mt-1.5 mr-1.5"
                      aria-label={`Inspect ${hit.label}`}
                      onClick={() => onInspect(hit.id)}
                    >
                      Inspect
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
