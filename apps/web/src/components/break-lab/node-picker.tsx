"use client";

/**
 * Picking a node out of the graph by name.
 *
 * Search hits the backend's own index rather than a client-side list, so it works on an
 * estate with thousands of fields. Results are filtered to the types the selected change
 * kind can actually apply to — offering a target the backend will reject is worse than
 * offering nothing.
 */

import { Check, Search, X } from "lucide-react";
import * as React from "react";
import { Badge, Button, Input, cx } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export interface PickerResult {
  id: string;
  label: string;
  type: string;
  description?: string;
  service?: string | null;
}

export function NodePicker({
  projectId,
  types,
  value,
  valueLabel,
  onChange,
  id,
  placeholder = "Search by name…",
  describedBy,
  invalid,
}: {
  projectId: string;
  /** Empty means "any type". */
  types: string[];
  value: string;
  valueLabel?: string;
  onChange: (node: PickerResult | null) => void;
  id: string;
  placeholder?: string;
  describedBy?: string;
  invalid?: boolean;
}) {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<PickerResult[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [touched, setTouched] = React.useState(false);

  React.useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const handle = window.setTimeout(() => {
      api
        .search(projectId, text)
        .then((payload) => {
          const rows = (payload.results ?? []) as PickerResult[];
          setResults(types.length ? rows.filter((row) => types.includes(row.type)) : rows);
        })
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query, projectId, types]);

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-3 py-2">
        <span className="flex min-w-0 items-center gap-2">
          <Check size={13} className="shrink-0 text-[var(--color-ok)]" aria-hidden />
          <span className="min-w-0">
            <span className="block truncate text-[13px] text-[var(--color-ink)]">
              {valueLabel || value}
            </span>
            <span className="mono block truncate text-[11px] text-[var(--color-dim)]">{value}</span>
          </span>
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            onChange(null);
            setQuery("");
            setResults([]);
          }}
          aria-label="Clear the selected target"
        >
          <X size={13} />
        </Button>
      </div>
    );
  }

  return (
    <div>
      <div className="relative">
        <Search
          size={13}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-dim)]"
          aria-hidden
        />
        <Input
          id={id}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setTouched(true);
          }}
          placeholder={placeholder}
          className="pl-8"
          autoComplete="off"
          role="combobox"
          aria-expanded={results.length > 0}
          aria-controls={`${id}-results`}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
        />
      </div>

      <div id={`${id}-results`} aria-live="polite">
        {loading && (
          <p className="mt-1.5 text-[12px] text-[var(--color-dim)]">Searching…</p>
        )}
        {!loading && touched && query.trim().length >= 2 && results.length === 0 && (
          <p className="mt-1.5 text-[12px] text-[var(--color-muted)]">
            Nothing matched
            {types.length ? ` among ${types.join(", ")} nodes` : ""}. Try a shorter word.
          </p>
        )}
        {results.length > 0 && (
          <ul
            className="mt-1.5 max-h-56 overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-surface)]"
            role="listbox"
            aria-label="Matching nodes"
          >
            {results.slice(0, 40).map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => {
                    onChange(row);
                    setQuery("");
                    setResults([]);
                  }}
                  className={cx(
                    "flex w-full items-start gap-2 px-2.5 py-2 text-left transition-colors",
                    "hover:bg-[var(--color-surface-2)]",
                  )}
                >
                  <Badge tone="neutral" className="mt-[1px] shrink-0">
                    {row.type}
                  </Badge>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] text-[var(--color-ink)]">
                      {row.label}
                    </span>
                    <span className="mono block truncate text-[11px] text-[var(--color-dim)]">
                      {row.id}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
