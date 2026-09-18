"use client";

/**
 * Command palette and global search.
 *
 * Searches the graph and the workspace sections in one list. Node results carry their
 * type and provenance so a dashed inference is never mistaken for a fact, even here.
 */

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Compass,
  CornerDownLeft,
  Download,
  FlaskConical,
  Gauge,
  MessageSquareText,
  Route,
  Settings as SettingsIcon,
  Swords,
  Target,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Badge, cx } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";

const SECTIONS = [
  { label: "Overview", href: "", icon: Gauge },
  { label: "Journeys", href: "/journeys", icon: Route },
  { label: "Galaxy", href: "/galaxy", icon: Compass },
  { label: "Ask", href: "/ask", icon: MessageSquareText },
  { label: "Break Lab", href: "/break-lab", icon: FlaskConical },
  { label: "Model Arena", href: "/arena", icon: Swords },
  { label: "Missions", href: "/missions", icon: Target },
  { label: "Reports", href: "/reports", icon: Download },
  { label: "Settings", href: "/settings", icon: SettingsIcon },
];

export function CommandPalette({ projectId }: { projectId: string }) {
  const open = useWorkspace((s) => s.commandOpen);
  const setOpen = useWorkspace((s) => s.setCommandOpen);
  const select = useWorkspace((s) => s.select);
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [cursor, setCursor] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Debounced so typing does not fire a request per keystroke.
  const [debounced, setDebounced] = React.useState("");
  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 160);
    return () => clearTimeout(timer);
  }, [query]);

  const { data, isFetching } = useQuery({
    queryKey: ["search", projectId, debounced],
    queryFn: () => api.search(projectId, debounced),
    enabled: open && debounced.length > 1,
  });

  const sectionMatches = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return SECTIONS;
    return SECTIONS.filter((s) => s.label.toLowerCase().includes(needle));
  }, [query]);

  const nodeMatches = data?.results ?? [];
  const total = sectionMatches.length + nodeMatches.length;

  React.useEffect(() => setCursor(0), [debounced, open]);
  React.useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
    else setQuery("");
  }, [open]);

  const go = React.useCallback(
    (index: number) => {
      if (index < sectionMatches.length) {
        const section = sectionMatches[index];
        router.push(`/workspace/${projectId}${section.href}`);
      } else {
        const node = nodeMatches[index - sectionMatches.length];
        if (!node) return;
        select(node.id);
        router.push(`/workspace/${projectId}/galaxy`);
      }
      setOpen(false);
    },
    [sectionMatches, nodeMatches, projectId, router, select, setOpen],
  );

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((c) => Math.min(c + 1, Math.max(0, total - 1)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(cursor);
    }
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          className="panel-raised fixed left-1/2 top-[14vh] z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden p-0 shadow-[var(--shadow-lift)]"
          aria-label="Command palette"
        >
          <DialogPrimitive.Title className="sr-only">Search and commands</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Type to search sections and graph nodes. Use arrow keys to move, Enter to open.
          </DialogPrimitive.Description>

          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search endpoints, schemas, fields, journeys…"
            className="h-12 w-full border-b border-[var(--color-line)] bg-transparent px-4 text-[14px] text-[var(--color-ink)] outline-none placeholder:text-[var(--color-dim)]"
            aria-label="Search"
            autoComplete="off"
          />

          <div className="max-h-[52vh] overflow-y-auto py-1.5" role="listbox">
            {sectionMatches.map((section, index) => {
              const Icon = section.icon;
              return (
                <Row
                  key={section.label}
                  active={cursor === index}
                  onSelect={() => go(index)}
                  onHover={() => setCursor(index)}
                >
                  <Icon size={14} className="shrink-0 text-[var(--color-dim)]" aria-hidden />
                  <span className="flex-1 truncate">{section.label}</span>
                  <span className="text-[11px] text-[var(--color-dim)]">Go to</span>
                </Row>
              );
            })}

            {nodeMatches.length > 0 && (
              <p className="px-4 pb-1 pt-3 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--color-dim)]">
                In this estate
              </p>
            )}
            {nodeMatches.map((node: any, index: number) => {
              const position = sectionMatches.length + index;
              return (
                <Row
                  key={node.id}
                  active={cursor === position}
                  onSelect={() => go(position)}
                  onHover={() => setCursor(position)}
                >
                  <span className="w-[62px] shrink-0 truncate text-[10.5px] uppercase tracking-wide text-[var(--color-dim)]">
                    {node.type}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{node.label}</span>
                  {!node.is_fact && (
                    <Badge tone="inferred" className="shrink-0">
                      inferred
                    </Badge>
                  )}
                  <ArrowRight size={12} className="shrink-0 text-[var(--color-dim)]" aria-hidden />
                </Row>
              );
            })}

            {debounced.length > 1 && !isFetching && nodeMatches.length === 0 && (
              <p className="px-4 py-6 text-center text-[12.5px] text-[var(--color-dim)]">
                Nothing in the estate matches “{debounced}”.
              </p>
            )}
          </div>

          <div className="flex items-center gap-3 border-t border-[var(--color-line)] px-4 py-2 text-[11px] text-[var(--color-dim)]">
            <span className="flex items-center gap-1">
              <CornerDownLeft size={11} aria-hidden /> open
            </span>
            <span>↑↓ move</span>
            <span>esc close</span>
            <span className="ml-auto">1–9 jump to a section</span>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function Row({
  active,
  onSelect,
  onHover,
  children,
}: {
  active: boolean;
  onSelect: () => void;
  onHover: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      role="option"
      aria-selected={active}
      onClick={onSelect}
      onMouseEnter={onHover}
      className={cx(
        "flex w-full items-center gap-2.5 px-4 py-2 text-left text-[12.5px] transition-colors",
        active ? "bg-[var(--color-surface-3)] text-[var(--color-ink)]" : "text-[var(--color-ink-2)]",
      )}
    >
      {children}
    </button>
  );
}
