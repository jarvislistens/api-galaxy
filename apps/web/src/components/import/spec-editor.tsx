"use client";

/**
 * The paste editor.
 *
 * CodeMirror touches `window` at module scope, so this file is only ever reached through
 * `next/dynamic({ ssr: false })` from `import-workbench.tsx`. Keeping it in its own module
 * is what makes that possible.
 */

import { json as jsonLanguage } from "@codemirror/lang-json";
import { yaml as yamlLanguage } from "@codemirror/lang-yaml";
import { oneDark } from "@codemirror/theme-one-dark";
import CodeMirror from "@uiw/react-codemirror";
import * as React from "react";

export interface SpecEditorProps {
  value: string;
  onChange: (value: string) => void;
  /** Which grammar to highlight with. Driven by the detected format, not by the filename. */
  language: "json" | "yaml";
  ariaLabel: string;
  /** 1-based line to mark as the parse failure, when the backend gave us one. */
  errorLine?: number | null;
}

export default function SpecEditor({
  value,
  onChange,
  language,
  ariaLabel,
  errorLine,
}: SpecEditorProps) {
  const extensions = React.useMemo(
    () => [language === "json" ? jsonLanguage() : yamlLanguage()],
    [language],
  );

  return (
    <div
      className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-line-strong)]"
      data-error-line={errorLine ?? undefined}
    >
      <CodeMirror
        value={value}
        onChange={onChange}
        height="360px"
        theme={oneDark}
        extensions={extensions}
        aria-label={ariaLabel}
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: true,
          autocompletion: false,
          bracketMatching: true,
        }}
      />
    </div>
  );
}
