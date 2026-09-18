"use client";

/**
 * Composing one change.
 *
 * The twelve change kinds, their legal target types and their parameters all come from the
 * backend, so this form is generated rather than hand-written — a thirteenth kind appears
 * here the moment the API knows about it. Everything is validated before submit so the
 * reader gets a field-level message instead of a 422.
 */

import { Zap } from "lucide-react";
import * as React from "react";
import { NodePicker, type PickerResult } from "@/components/break-lab/node-picker";
import {
  Button,
  Card,
  Field,
  InfoNote,
  Input,
  SectionTitle,
  Select,
} from "@/components/ui/primitives";

export interface ChangeKind {
  id: string;
  label: string;
  target_types: string[];
  params: { name: string; type: string; required: string | boolean }[];
}

export interface ChangeDraft {
  kind: string;
  target_id: string;
  params: Record<string, any>;
  label: string;
}

const PARAM_LABEL: Record<string, string> = {
  new_name: "New name",
  new_type: "New type",
  new_format: "New format",
  required: "Required",
  status: "Status code",
  action: "Action",
  new_schema: "Replacement schema",
  domain_id: "Target domain",
  latency_ms: "Added latency (ms)",
  other_id: "The other field",
};

const PARAM_HINT: Record<string, string> = {
  new_type: "A JSON Schema type: string, integer, number, boolean, array or object.",
  new_format: "Optional. For example date-time, uuid or int64.",
  status: "The HTTP status of the response being changed, for example 200 or 404.",
  latency_ms: "Whole milliseconds. Models reachability only, not queueing or retries.",
};

/** `"'remove' | 'replace'"` is the backend's way of declaring an enum. */
function enumOptions(type: string): string[] | null {
  const matches = [...type.matchAll(/'([^']+)'/g)].map((match) => match[1]);
  return matches.length >= 2 ? matches : null;
}

function isRequired(value: string | boolean): boolean {
  return value === true || value === "true";
}

export function ChangeBuilder({
  projectId,
  kinds,
  onSubmit,
  disabled,
  pending,
  disabledReason,
}: {
  projectId: string;
  kinds: ChangeKind[];
  onSubmit: (draft: ChangeDraft) => void;
  disabled?: boolean;
  pending?: boolean;
  disabledReason?: string;
}) {
  const [kindId, setKindId] = React.useState("");
  const [target, setTarget] = React.useState<PickerResult | null>(null);
  const [params, setParams] = React.useState<Record<string, string>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  const kind = kinds.find((item) => item.id === kindId) ?? null;

  // Changing the kind invalidates the target and the parameters — they belong to it.
  const pickKind = (next: string) => {
    setKindId(next);
    setTarget(null);
    setParams({});
    setErrors({});
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!kind) next.kind = "Choose what kind of change to make.";
    if (!target) next.target = "Choose the node this change applies to.";
    for (const param of kind?.params ?? []) {
      const raw = (params[param.name] ?? "").trim();
      if (!raw) {
        if (isRequired(param.required)) next[param.name] = "This is required.";
        continue;
      }
      if (param.type === "integer" && !/^-?\d+$/.test(raw)) {
        next[param.name] = "Enter a whole number.";
      }
      if (param.type === "boolean" && !["true", "false"].includes(raw)) {
        next[param.name] = "Choose yes or no.";
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!validate() || !kind || !target) return;
    const typed: Record<string, any> = {};
    for (const param of kind.params) {
      const raw = (params[param.name] ?? "").trim();
      if (!raw) continue;
      typed[param.name] =
        param.type === "integer"
          ? Number.parseInt(raw, 10)
          : param.type === "boolean"
            ? raw === "true"
            : raw;
    }
    onSubmit({
      kind: kind.id,
      target_id: target.id,
      params: typed,
      label: `${kind.label} — ${target.label}`,
    });
    setParams({});
    setErrors({});
  };

  return (
    <Card className="p-5">
      <SectionTitle>Make a change</SectionTitle>

      <form onSubmit={submit} noValidate className="space-y-4">
        <Field label="Change kind" error={errors.kind}>
          <Select
            value={kindId}
            onChange={(event) => pickKind(event.target.value)}
            disabled={disabled}
          >
            <option value="">Choose a change…</option>
            {kinds.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </Select>
        </Field>

        {kind && (
          <div className="space-y-1.5">
            <label
              htmlFor="change-target"
              className="block text-[12.5px] font-medium text-[var(--color-ink-2)]"
            >
              Target
            </label>
            <NodePicker
              id="change-target"
              projectId={projectId}
              types={kind.target_types}
              value={target?.id ?? ""}
              valueLabel={target?.label}
              onChange={setTarget}
              placeholder={`Search ${kind.target_types.join(" / ")}…`}
              describedBy="change-target-hint"
              invalid={Boolean(errors.target)}
            />
            {errors.target ? (
              <p role="alert" className="text-[12px] text-[var(--color-broken)]">
                {errors.target}
              </p>
            ) : (
              <p id="change-target-hint" className="text-[12px] text-[var(--color-dim)]">
                Only {kind.target_types.join(", ")} nodes can take this change.
              </p>
            )}
          </div>
        )}

        {kind?.params.map((param) => {
          const options = enumOptions(param.type);
          const label = `${PARAM_LABEL[param.name] ?? param.name.replace(/_/g, " ")}${
            isRequired(param.required) ? "" : " (optional)"
          }`;
          const value = params[param.name] ?? "";
          const set = (next: string) =>
            setParams((current) => ({ ...current, [param.name]: next }));

          if (param.name.endsWith("_id") && !options) {
            return (
              <div key={param.name} className="space-y-1.5">
                <label
                  htmlFor={`param-${param.name}`}
                  className="block text-[12.5px] font-medium text-[var(--color-ink-2)]"
                >
                  {label}
                </label>
                <NodePicker
                  id={`param-${param.name}`}
                  projectId={projectId}
                  types={param.name === "domain_id" ? ["Domain"] : []}
                  value={value}
                  onChange={(node) => set(node?.id ?? "")}
                  placeholder="Search the graph…"
                  invalid={Boolean(errors[param.name])}
                />
                {errors[param.name] && (
                  <p role="alert" className="text-[12px] text-[var(--color-broken)]">
                    {errors[param.name]}
                  </p>
                )}
              </div>
            );
          }

          return (
            <Field
              key={param.name}
              label={label}
              hint={PARAM_HINT[param.name]}
              error={errors[param.name]}
            >
              {options ? (
                <Select value={value} onChange={(event) => set(event.target.value)}>
                  <option value="">Choose…</option>
                  {options.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              ) : param.type === "boolean" ? (
                <Select value={value} onChange={(event) => set(event.target.value)}>
                  <option value="">Choose…</option>
                  <option value="true">Yes — make it required</option>
                  <option value="false">No — make it optional</option>
                </Select>
              ) : (
                <Input
                  type={param.type === "integer" ? "number" : "text"}
                  inputMode={param.type === "integer" ? "numeric" : undefined}
                  value={value}
                  onChange={(event) => set(event.target.value)}
                />
              )}
            </Field>
          );
        })}

        <div className="flex items-center gap-3 pt-1">
          <Button type="submit" variant="primary" disabled={disabled} loading={pending}>
            <Zap size={14} aria-hidden />
            Apply change
          </Button>
          {disabled && disabledReason && (
            <p className="text-[12px] text-[var(--color-muted)]">{disabledReason}</p>
          )}
        </div>
      </form>

      {!kind && (
        <div className="mt-4">
          <InfoNote>
            Twelve change kinds, all computed the same way: the graph is cloned, the change is
            applied to the clone, and impact is a traversal of what depends on what.
          </InfoNote>
        </div>
      )}
    </Card>
  );
}
