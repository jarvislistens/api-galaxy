"use client";

/**
 * The design system's building blocks.
 *
 * These wrap Radix where accessibility is hard to get right by hand (dialog, tooltip,
 * tabs) and are plain elements where it is not. Every interactive element here is
 * keyboard reachable and has a visible focus ring inherited from `globals.css`.
 */

import * as AccordionPrimitive from "@radix-ui/react-accordion";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import clsx from "clsx";
import { ChevronDown, Info, Loader2, X } from "lucide-react";
import * as React from "react";

export const cx = clsx;

/* ------------------------------------------------------------------ Button */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "quiet";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 font-medium rounded-[var(--radius-sm)] " +
  "transition-[background,border-color,color,transform] duration-150 ease-[var(--ease-out-quint)] " +
  "disabled:opacity-40 disabled:pointer-events-none select-none whitespace-nowrap";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--color-accent)] text-[#0a0c10] hover:bg-[var(--color-accent-soft)] " +
    "active:translate-y-[0.5px] font-semibold",
  secondary:
    "bg-[var(--color-surface-2)] text-[var(--color-ink)] border border-[var(--color-line-strong)] " +
    "hover:bg-[var(--color-surface-3)] hover:border-[var(--color-dim)]",
  ghost:
    "text-[var(--color-ink-2)] hover:text-[var(--color-ink)] hover:bg-[var(--color-surface-2)] " +
    "border border-transparent",
  danger:
    "bg-[color-mix(in_oklab,var(--color-broken)_18%,transparent)] text-[var(--color-broken)] " +
    "border border-[color-mix(in_oklab,var(--color-broken)_38%,transparent)] " +
    "hover:bg-[color-mix(in_oklab,var(--color-broken)_26%,transparent)]",
  quiet: "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
};

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-[12px]",
  md: "h-9 px-3.5 text-[13px]",
  lg: "h-11 px-5 text-[14px]",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cx(BUTTON_BASE, BUTTON_VARIANT[variant], BUTTON_SIZE[size], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 size={14} className="animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

/* --------------------------------------------------------------------- Card */

export function Card({
  className,
  raised,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { raised?: boolean }) {
  return <div className={cx(raised ? "panel-raised" : "panel", className)} {...rest} />;
}

/* -------------------------------------------------------------------- Badge */

export type BadgeTone =
  | "neutral" | "accent" | "fact" | "inferred" | "user"
  | "broken" | "degraded" | "ok" | "possible";

const BADGE_TONE: Record<BadgeTone, string> = {
  neutral: "bg-[var(--color-surface-3)] text-[var(--color-ink-2)] border-[var(--color-line-strong)]",
  accent:
    "bg-[color-mix(in_oklab,var(--color-accent)_16%,transparent)] text-[var(--color-accent-soft)] " +
    "border-[color-mix(in_oklab,var(--color-accent)_34%,transparent)]",
  fact:
    "bg-[color-mix(in_oklab,var(--color-fact)_14%,transparent)] text-[var(--color-fact)] " +
    "border-[color-mix(in_oklab,var(--color-fact)_32%,transparent)]",
  inferred:
    "bg-[color-mix(in_oklab,var(--color-inferred)_14%,transparent)] text-[var(--color-inferred)] " +
    "border-[color-mix(in_oklab,var(--color-inferred)_34%,transparent)]",
  user:
    "bg-[color-mix(in_oklab,var(--color-user)_14%,transparent)] text-[var(--color-user)] " +
    "border-[color-mix(in_oklab,var(--color-user)_34%,transparent)]",
  broken:
    "bg-[color-mix(in_oklab,var(--color-broken)_16%,transparent)] text-[var(--color-broken)] " +
    "border-[color-mix(in_oklab,var(--color-broken)_36%,transparent)]",
  degraded:
    "bg-[color-mix(in_oklab,var(--color-degraded)_16%,transparent)] text-[var(--color-degraded)] " +
    "border-[color-mix(in_oklab,var(--color-degraded)_36%,transparent)]",
  ok:
    "bg-[color-mix(in_oklab,var(--color-ok)_14%,transparent)] text-[var(--color-ok)] " +
    "border-[color-mix(in_oklab,var(--color-ok)_32%,transparent)]",
  possible:
    "bg-[var(--color-surface-3)] text-[var(--color-possible)] border-[var(--color-line-strong)]",
};

export function Badge({
  tone = "neutral",
  icon,
  children,
  className,
  ...rest
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone; icon?: React.ReactNode }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-[2px] text-[11px] font-medium leading-4",
        BADGE_TONE[tone],
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ Tooltip */

export function TooltipRoot({ children }: { children: React.ReactNode }) {
  return <TooltipPrimitive.Provider delayDuration={220}>{children}</TooltipPrimitive.Provider>;
}

export function Tooltip({
  label,
  children,
  side = "top",
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-[300px] rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2.5 py-1.5 text-[12px] leading-snug text-[var(--color-ink-2)] shadow-[var(--shadow-lift)]"
        >
          {label}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

/* ------------------------------------------------------------------- Dialog */

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/65 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          className={cx(
            "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2",
            "panel-raised max-h-[86vh] overflow-y-auto p-5 shadow-[var(--shadow-lift)]",
            wide ? "max-w-3xl" : "max-w-lg",
          )}
        >
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <DialogPrimitive.Title className="text-[16px] font-semibold text-[var(--color-ink)]">
                {title}
              </DialogPrimitive.Title>
              {description && (
                <DialogPrimitive.Description className="mt-1 text-[13px] text-[var(--color-muted)]">
                  {description}
                </DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close asChild>
              <Button variant="ghost" size="sm" aria-label="Close">
                <X size={14} />
              </Button>
            </DialogPrimitive.Close>
          </div>
          {children}
          {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/* --------------------------------------------------------------------- Tabs */

export const Tabs = TabsPrimitive.Root;

export function TabsBar({ className, ...rest }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cx(
        "flex items-center gap-1 rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface)] p-1",
        className,
      )}
      {...rest}
    />
  );
}

export function Tab({ className, ...rest }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cx(
        "rounded-[var(--radius-xs)] px-3 py-1.5 text-[12.5px] font-medium text-[var(--color-muted)]",
        "transition-colors duration-150 hover:text-[var(--color-ink)]",
        "data-[state=active]:bg-[var(--color-surface-3)] data-[state=active]:text-[var(--color-ink)]",
        className,
      )}
      {...rest}
    />
  );
}

export const TabPanel = TabsPrimitive.Content;

/* ---------------------------------------------------------------- Accordion */

export function Accordion({ children, ...rest }: React.ComponentProps<typeof AccordionPrimitive.Root>) {
  return (
    <AccordionPrimitive.Root {...rest}>{children}</AccordionPrimitive.Root>
  );
}

export function AccordionItem({
  value,
  trigger,
  children,
}: {
  value: string;
  trigger: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <AccordionPrimitive.Item value={value} className="border-b border-[var(--color-line)]">
      <AccordionPrimitive.Header>
        <AccordionPrimitive.Trigger className="group flex w-full items-center justify-between gap-3 py-3 text-left text-[13px] font-medium text-[var(--color-ink)] hover:text-[var(--color-accent-soft)]">
          {trigger}
          <ChevronDown
            size={15}
            className="shrink-0 text-[var(--color-dim)] transition-transform duration-200 group-data-[state=open]:rotate-180"
            aria-hidden
          />
        </AccordionPrimitive.Trigger>
      </AccordionPrimitive.Header>
      <AccordionPrimitive.Content className="overflow-hidden pb-3 text-[13px] text-[var(--color-muted)]">
        {children}
      </AccordionPrimitive.Content>
    </AccordionPrimitive.Item>
  );
}

/* ------------------------------------------------------------------- Switch */

export function Switch({
  checked,
  onCheckedChange,
  label,
  description,
  id,
}: {
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
  label: string;
  description?: string;
  id?: string;
}) {
  const inputId = id ?? React.useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={inputId} className="block text-[13px] font-medium text-[var(--color-ink)]">
          {label}
        </label>
        {description && (
          <p className="mt-0.5 text-[12px] leading-snug text-[var(--color-muted)]">{description}</p>
        )}
      </div>
      <SwitchPrimitive.Root
        id={inputId}
        checked={checked}
        onCheckedChange={onCheckedChange}
        className={cx(
          "relative h-[22px] w-[38px] shrink-0 rounded-full border transition-colors duration-200",
          checked
            ? "border-[var(--color-accent)] bg-[var(--color-accent)]"
            : "border-[var(--color-line-strong)] bg-[var(--color-surface-3)]",
        )}
      >
        <SwitchPrimitive.Thumb
          className={cx(
            "block h-[16px] w-[16px] rounded-full bg-white shadow transition-transform duration-200",
            "translate-x-[3px] data-[state=checked]:translate-x-[19px]",
          )}
        />
      </SwitchPrimitive.Root>
    </div>
  );
}

/* --------------------------------------------------------------------- Form */

export function Field({
  label,
  hint,
  error,
  children,
  id,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
  id?: string;
}) {
  const fieldId = id ?? React.useId();
  const describedBy = [hint ? `${fieldId}-hint` : null, error ? `${fieldId}-error` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="space-y-1.5">
      <label htmlFor={fieldId} className="block text-[12.5px] font-medium text-[var(--color-ink-2)]">
        {label}
      </label>
      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement<any>, {
            id: fieldId,
            "aria-describedby": describedBy || undefined,
            "aria-invalid": error ? true : undefined,
          })
        : children}
      {hint && !error && (
        <p id={`${fieldId}-hint`} className="text-[12px] text-[var(--color-dim)]">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${fieldId}-error`} role="alert" className="text-[12px] text-[var(--color-broken)]">
          {error}
        </p>
      )}
    </div>
  );
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={cx(
          "h-9 w-full rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)]",
          "px-3 text-[13px] text-[var(--color-ink)] placeholder:text-[var(--color-dim)]",
          "transition-colors duration-150 focus:border-[var(--color-accent)]",
          className,
        )}
        {...rest}
      />
    );
  },
);

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(function Select({ className, children, ...rest }, ref) {
  return (
    <select
      ref={ref}
      className={cx(
        "h-9 w-full rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)]",
        "px-2.5 text-[13px] text-[var(--color-ink)] focus:border-[var(--color-accent)]",
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  );
});

/* ------------------------------------------------------------------- States */

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  body: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      {icon && <div className="text-[var(--color-dim)]">{icon}</div>}
      <h3 className="text-[15px] font-medium text-[var(--color-ink)]">{title}</h3>
      <p className="max-w-md text-[13px] leading-relaxed text-[var(--color-muted)]">{body}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  detail,
  hint,
  correlationId,
  onRetry,
}: {
  title?: string;
  detail: string;
  hint?: string;
  correlationId?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-[var(--radius-md)] border border-[color-mix(in_oklab,var(--color-broken)_38%,transparent)] bg-[color-mix(in_oklab,var(--color-broken)_10%,transparent)] p-4"
    >
      <p className="text-[13px] font-semibold text-[var(--color-broken)]">{title}</p>
      <p className="mt-1 text-[13px] text-[var(--color-ink-2)]">{detail}</p>
      {hint && <p className="mt-1 text-[12px] text-[var(--color-muted)]">{hint}</p>}
      {correlationId && (
        <p className="mono mt-2 text-[11px] text-[var(--color-dim)]">
          Correlation ID {correlationId}
        </p>
      )}
      {onRetry && (
        <Button size="sm" variant="secondary" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden />;
}

export function LoadingBlock({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className={cx("h-4", index === 0 ? "w-1/3" : "w-full")} />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-3)]"
    >
      <div
        className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-300 ease-[var(--ease-out-quint)]"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------- Detail */

export function KeyValue({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[104px_1fr] gap-3 py-1.5 text-[12.5px]">
      <dt className="text-[var(--color-dim)]">{label}</dt>
      <dd className="min-w-0 break-words text-[var(--color-ink-2)]">{children}</dd>
    </div>
  );
}

export function SectionTitle({
  children,
  action,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-[13px] font-semibold tracking-tight text-[var(--color-ink)]">{children}</h2>
      {action}
    </div>
  );
}

export function InfoNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-[12px] leading-snug text-[var(--color-muted)]">
      <Info size={13} className="mt-[2px] shrink-0 text-[var(--color-dim)]" aria-hidden />
      <span>{children}</span>
    </p>
  );
}
