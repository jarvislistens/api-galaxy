"use client";

/**
 * Drag-and-drop plus a real file picker.
 *
 * The drop zone is a `<label>` wrapping a real `<input type="file">`, so it is reachable
 * with a keyboard and announced correctly without any ARIA at all. Drag-and-drop is the
 * enhancement, not the mechanism.
 */

import { UploadCloud } from "lucide-react";
import * as React from "react";
import { cx } from "@/components/ui/primitives";

export function FileIntake({
  accept,
  onFiles,
  headline,
  help,
  id,
  disabled,
}: {
  accept: string;
  onFiles: (files: File[]) => void;
  headline: string;
  help: React.ReactNode;
  id: string;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  const extensions = React.useMemo(
    () => accept.split(",").map((part) => part.trim().toLowerCase()).filter(Boolean),
    [accept],
  );

  const accepted = React.useCallback(
    (files: File[]) =>
      files.filter((file) => extensions.some((ext) => file.name.toLowerCase().endsWith(ext))),
    [extensions],
  );

  return (
    <div>
      <label
        htmlFor={id}
        onDragOver={(event) => {
          if (disabled) return;
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          if (disabled) return;
          event.preventDefault();
          setDragging(false);
          const dropped = accepted(Array.from(event.dataTransfer.files));
          if (dropped.length) onFiles(dropped);
        }}
        className={cx(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[var(--radius-lg)]",
          "border border-dashed px-6 py-10 text-center transition-colors duration-200",
          disabled && "cursor-not-allowed opacity-50",
          dragging
            ? "border-[var(--color-accent)] bg-[color-mix(in_oklab,var(--color-accent)_8%,transparent)]"
            : "border-[var(--color-line-strong)] bg-[var(--color-surface)] hover:border-[var(--color-dim)]",
        )}
      >
        <UploadCloud
          size={22}
          className={dragging ? "text-[var(--color-accent-soft)]" : "text-[var(--color-dim)]"}
          aria-hidden
        />
        <span className="text-[13.5px] font-medium text-[var(--color-ink)]">{headline}</span>
        <span className="max-w-md text-[12px] leading-snug text-[var(--color-muted)]">{help}</span>
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept={accept}
          multiple
          disabled={disabled}
          className="sr-only"
          onChange={(event) => {
            const picked = Array.from(event.target.files ?? []);
            if (picked.length) onFiles(picked);
            // Reset so picking the same file twice still fires a change event.
            event.target.value = "";
          }}
        />
      </label>
    </div>
  );
}
