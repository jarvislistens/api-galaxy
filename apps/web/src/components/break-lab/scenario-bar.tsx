"use client";

/**
 * Choosing or creating the sandbox.
 *
 * A scenario is a clone of the graph with a list of changes applied on top. The base
 * project is never touched, and that promise is repeated here as standing copy rather than
 * hidden in a tooltip, because it is the reason anyone is willing to press these buttons.
 */

import { FlaskConical, Plus, RotateCcw, ShieldCheck, Trash2 } from "lucide-react";
import * as React from "react";
import {
  Badge,
  Button,
  Dialog,
  Field,
  Input,
  Select,
  cx,
} from "@/components/ui/primitives";
import type { Scenario } from "@/lib/types";

export function ScenarioBar({
  scenarios,
  activeId,
  onSelect,
  onCreate,
  onReset,
  onDelete,
  busy,
  creating,
}: {
  scenarios: Scenario[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onCreate: (name: string, description: string) => void;
  onReset: () => void;
  onDelete: () => void;
  busy?: boolean;
  creating?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [nameError, setNameError] = React.useState<string | null>(null);

  const active = scenarios.find((scenario) => scenario.id === activeId) ?? null;

  const submit = () => {
    if (!name.trim()) {
      setNameError("Give the scenario a name so you can tell two of them apart.");
      return;
    }
    setNameError(null);
    onCreate(name.trim(), description.trim());
    setName("");
    setDescription("");
    setOpen(false);
  };

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-[var(--color-line)] bg-[var(--color-surface)]/40 px-5 py-3">
      <FlaskConical size={15} className="shrink-0 text-[var(--color-accent-soft)]" aria-hidden />

      <div className="w-[260px] shrink-0">
        <label htmlFor="scenario-select" className="sr-only">
          Active scenario
        </label>
        <Select
          id="scenario-select"
          value={activeId ?? ""}
          disabled={busy}
          onChange={(event) => onSelect(event.target.value || null)}
        >
          <option value="">No scenario — pick or create one</option>
          {scenarios.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.name} ({scenario.change_count ?? scenario.changes.length} change
              {(scenario.change_count ?? scenario.changes.length) === 1 ? "" : "s"})
            </option>
          ))}
        </Select>
      </div>

      <Button variant="secondary" onClick={() => setOpen(true)} disabled={busy} loading={creating}>
        <Plus size={14} aria-hidden />
        New scenario
      </Button>

      {active && (
        <>
          <Badge tone="degraded">Scenario active</Badge>
          <Button variant="ghost" onClick={onReset} disabled={busy} aria-label="Reset this scenario">
            <RotateCcw size={14} aria-hidden />
            Reset
          </Button>
          <Button
            variant="ghost"
            onClick={() => setConfirmDelete(true)}
            disabled={busy}
            aria-label="Delete this scenario"
          >
            <Trash2 size={14} aria-hidden />
            Delete
          </Button>
        </>
      )}

      <p
        className={cx(
          "ml-auto flex items-center gap-1.5 text-[11.5px] leading-snug text-[var(--color-dim)]",
        )}
      >
        <ShieldCheck size={12} className="shrink-0 text-[var(--color-ok)]" aria-hidden />
        The base project is never modified. Everything here happens in a clone.
      </p>

      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="New scenario"
        description="A named sandbox. Changes you add here apply to a clone of the graph, never to the imported specification."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={submit}>
              Create scenario
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Name" error={nameError ?? undefined}>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Rename customer email"
              autoFocus
            />
          </Field>
          <Field label="Description" hint="Optional. Useful when you share the change summary.">
            <Input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What are we testing, and why"
            />
          </Field>
        </div>
      </Dialog>

      <Dialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete "${active?.name ?? ""}"?`}
        description="The scenario, its changes and its applied repairs are removed. The imported project is untouched."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              Keep it
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setConfirmDelete(false);
                onDelete();
              }}
            >
              Delete scenario
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-[var(--color-muted)]">
          This cannot be undone. Export the change summary first if you need a record.
        </p>
      </Dialog>
    </div>
  );
}
