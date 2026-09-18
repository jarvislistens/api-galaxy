"use client";

/**
 * The workspace frame: compact left navigation, top command bar, and the page body.
 *
 * Three panels at desktop width; at narrow widths the side panels become drawers so the
 * canvas keeps the whole screen. Optimised for a 1440px screen-share, functional at 1024.
 */

import {
  Boxes,
  Compass,
  Download,
  FlaskConical,
  Gauge,
  Layers,
  type LucideIcon,
  MessageSquareText,
  PanelRightClose,
  PanelRightOpen,
  Redo2,
  Route,
  Search,
  Settings as SettingsIcon,
  Swords,
  Target,
  Undo2,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { CommandPalette } from "@/components/workspace/command-palette";
import { ProviderIndicator } from "@/components/workspace/provider-indicator";
import { Badge, Button, Tooltip, cx } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  hint: string;
}

const NAV: NavItem[] = [
  { href: "", label: "Overview", icon: Gauge, hint: "What is in this estate" },
  { href: "/journeys", label: "Journeys", icon: Route, hint: "Play a business flow" },
  { href: "/galaxy", label: "Galaxy", icon: Compass, hint: "The interactive graph" },
  { href: "/ask", label: "Ask", icon: MessageSquareText, hint: "Question the graph" },
  { href: "/break-lab", label: "Break Lab", icon: FlaskConical, hint: "Simulate a change" },
  { href: "/arena", label: "Model Arena", icon: Swords, hint: "Compare providers" },
  { href: "/missions", label: "Missions", icon: Target, hint: "Learn by doing" },
  { href: "/reports", label: "Reports", icon: Download, hint: "Export and share" },
  { href: "/settings", label: "Settings", icon: SettingsIcon, hint: "Providers and privacy" },
];

export function WorkspaceShell({
  projectId,
  children,
}: {
  projectId: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const setProject = useWorkspace((s) => s.setProject);
  const setCommandOpen = useWorkspace((s) => s.setCommandOpen);
  const inspectorOpen = useWorkspace((s) => s.inspectorOpen);
  const setInspectorOpen = useWorkspace((s) => s.setInspectorOpen);
  const undoStack = useWorkspace((s) => s.undoStack);
  const redoStack = useWorkspace((s) => s.redoStack);
  const undo = useWorkspace((s) => s.undo);
  const redo = useWorkspace((s) => s.redo);
  const activeScenarioId = useWorkspace((s) => s.activeScenarioId);

  React.useEffect(() => {
    setProject(projectId);
  }, [projectId, setProject]);

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
  });

  // Global shortcuts. Kept few and conventional so they do not have to be learned.
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) void redo();
        else void undo();
        return;
      }
      if (typing) return;
      if (event.key === "/") {
        event.preventDefault();
        setCommandOpen(true);
      }
      if (event.key === "i") setInspectorOpen(!inspectorOpen);
      // 1–9 jump to a section, matching the order in the sidebar.
      const index = Number.parseInt(event.key, 10);
      if (!Number.isNaN(index) && index >= 1 && index <= NAV.length) {
        router.push(`/workspace/${projectId}${NAV[index - 1].href}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [projectId, router, setCommandOpen, setInspectorOpen, inspectorOpen, undo, redo]);

  const base = `/workspace/${projectId}`;
  const stats = project?.stats;

  return (
    <div className="flex h-[100svh] flex-col overflow-hidden bg-[var(--color-base)]">
      {/* ---------------------------------------------------------- top bar */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[var(--color-line)] px-3">
        <Link href="/" className="flex items-center gap-2 pr-2" aria-label="API Galaxy home">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle cx="12" cy="12" r="2.6" fill="var(--color-accent)" />
            <ellipse cx="12" cy="12" rx="10" ry="4.2" stroke="var(--color-cyan)" strokeOpacity=".7"
                     strokeWidth="1.1" transform="rotate(-28 12 12)" />
            <ellipse cx="12" cy="12" rx="10" ry="4.2" stroke="var(--color-violet)" strokeOpacity=".5"
                     strokeWidth="1.1" transform="rotate(34 12 12)" />
          </svg>
        </Link>

        <div className="flex min-w-0 items-baseline gap-2">
          <h1 className="truncate text-[13px] font-semibold text-[var(--color-ink)]">
            {project?.name ?? "Loading…"}
          </h1>
          {project?.is_demo && (
            <Badge tone="accent" className="shrink-0">
              Demo data
            </Badge>
          )}
          {activeScenarioId && (
            <Badge tone="degraded" className="shrink-0">
              Scenario active
            </Badge>
          )}
        </div>

        {stats && (
          <div className="hidden items-center gap-3 text-[11.5px] text-[var(--color-dim)] lg:flex">
            <Counter value={stats.services} label="services" />
            <Counter value={stats.operations} label="ops" />
            <Counter value={stats.schemas} label="schemas" />
            <Counter value={stats.risks} label="findings" />
          </div>
        )}

        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={() => setCommandOpen(true)}
            className="flex h-8 items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2.5 text-[12px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-dim)] hover:text-[var(--color-ink)]"
            aria-label="Search and commands"
          >
            <Search size={13} aria-hidden />
            <span className="hidden sm:inline">Search</span>
            <kbd className="mono hidden rounded border border-[var(--color-line-strong)] px-1 text-[10px] text-[var(--color-dim)] sm:inline">
              ⌘K
            </kbd>
          </button>

          <Tooltip label="Undo (⌘Z)">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void undo()}
              disabled={!undoStack.length}
              aria-label="Undo"
            >
              <Undo2 size={14} />
            </Button>
          </Tooltip>
          <Tooltip label="Redo (⇧⌘Z)">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void redo()}
              disabled={!redoStack.length}
              aria-label="Redo"
            >
              <Redo2 size={14} />
            </Button>
          </Tooltip>

          <ProviderIndicator />

          <Tooltip label="Export this project">
            <Button variant="ghost" size="sm" onClick={() => router.push(`${base}/reports`)}
                    aria-label="Export">
              <Download size={14} />
            </Button>
          </Tooltip>

          <Tooltip label={inspectorOpen ? "Hide inspector (i)" : "Show inspector (i)"}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setInspectorOpen(!inspectorOpen)}
              aria-label={inspectorOpen ? "Hide inspector" : "Show inspector"}
              aria-pressed={inspectorOpen}
            >
              {inspectorOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
            </Button>
          </Tooltip>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* ------------------------------------------------------ left nav */}
        <nav
          className="flex w-[58px] shrink-0 flex-col items-center gap-0.5 border-r border-[var(--color-line)] py-2 xl:w-[188px] xl:items-stretch xl:px-2"
          aria-label="Workspace sections"
        >
          {NAV.map((item, index) => {
            const href = `${base}${item.href}`;
            const active = item.href === "" ? pathname === base : pathname.startsWith(href);
            const Icon = item.icon;
            return (
              <Tooltip key={item.label} label={`${item.hint} · press ${index + 1}`} side="right">
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cx(
                    "flex items-center gap-2.5 rounded-[var(--radius-sm)] px-2 py-2 text-[12.5px] transition-colors duration-150",
                    "justify-center xl:justify-start",
                    active
                      ? "bg-[var(--color-surface-3)] text-[var(--color-ink)]"
                      : "text-[var(--color-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-ink)]",
                  )}
                >
                  <Icon size={16} aria-hidden className="shrink-0" />
                  <span className="hidden xl:inline">{item.label}</span>
                </Link>
              </Tooltip>
            );
          })}

          <div className="mt-auto hidden px-2 pb-1 xl:block">
            <p className="text-[10.5px] leading-tight text-[var(--color-dim)]">
              Everything stays on this machine unless you explicitly consent.
            </p>
          </div>
          <Layers size={14} className="mt-auto text-[var(--color-dim)] xl:hidden" aria-hidden />
        </nav>

        {/* ---------------------------------------------------------- body */}
        <main id="main" className="min-w-0 flex-1 overflow-hidden">
          {children}
        </main>
      </div>

      <CommandPalette projectId={projectId} />
    </div>
  );
}

function Counter({ value, label }: { value?: number; label: string }) {
  if (value === undefined) return null;
  return (
    <span className="flex items-baseline gap-1">
      <span className="numeral text-[12px] font-medium text-[var(--color-ink-2)]">{value}</span>
      <span>{label}</span>
    </span>
  );
}

/** A right-hand inspector rail that pages can opt into. */
export function InspectorRail({ children }: { children: React.ReactNode }) {
  const open = useWorkspace((s) => s.inspectorOpen);
  if (!open) return null;
  return (
    <aside
      className="w-[330px] shrink-0 overflow-y-auto border-l border-[var(--color-line)] bg-[var(--color-surface)]/50 2xl:w-[380px]"
      aria-label="Inspector"
    >
      {children}
    </aside>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  icon: Icon,
}: {
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[var(--color-line)] px-5 py-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={15} className="text-[var(--color-accent-soft)]" aria-hidden />}
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-ink)]">
            {title}
          </h2>
        </div>
        {subtitle && (
          <p className="mt-1 max-w-3xl text-[12.5px] leading-snug text-[var(--color-muted)]">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export { Boxes };
