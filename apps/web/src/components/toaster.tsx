"use client";

/**
 * Toasts are for transient confirmations only.
 *
 * Anything the user has to act on — a failed import, a provider that is unreachable —
 * stays on the page as an `ErrorState`. A message that disappears is not an error report.
 */

import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import * as React from "react";
import { useWorkspace } from "@/lib/store";

const ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
} as const;

const TONE = {
  info: "text-[var(--color-ink-2)]",
  success: "text-[var(--color-ok)]",
  warning: "text-[var(--color-degraded)]",
  error: "text-[var(--color-broken)]",
} as const;

export function Toaster() {
  const toasts = useWorkspace((s) => s.toasts);
  const dismiss = useWorkspace((s) => s.dismissToast);

  React.useEffect(() => {
    if (!toasts.length) return;
    const timers = toasts.map((toast) =>
      setTimeout(() => dismiss(toast.id), toast.tone === "error" ? 8000 : 4200),
    );
    return () => timers.forEach(clearTimeout);
  }, [toasts, dismiss]);

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[340px] max-w-[calc(100vw-2rem)] flex-col gap-2"
      role="status"
      aria-live="polite"
    >
      <AnimatePresence initial={false}>
        {toasts.map((toast) => {
          const Icon = ICONS[toast.tone];
          return (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: 8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.98 }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
              className="panel-raised pointer-events-auto flex items-start gap-2.5 p-3"
            >
              <Icon size={15} className={`mt-[1px] shrink-0 ${TONE[toast.tone]}`} aria-hidden />
              <p className="flex-1 text-[12.5px] leading-snug text-[var(--color-ink-2)]">
                {toast.text}
              </p>
              <button
                onClick={() => dismiss(toast.id)}
                className="text-[var(--color-dim)] hover:text-[var(--color-ink)]"
                aria-label="Dismiss"
              >
                <XCircle size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
