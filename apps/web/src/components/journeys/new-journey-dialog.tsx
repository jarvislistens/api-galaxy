"use client";

/**
 * Compose a journey by picking operations in call order.
 *
 * Order is the whole point, so the chosen list is explicit and reorderable rather than a
 * set of checkboxes that silently sorts itself. Anything created here is labelled as your
 * edit in the graph, never as a specification fact.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import * as React from "react";
import {
  Button,
  Dialog,
  ErrorState,
  Field,
  InfoNote,
  Input,
  LoadingBlock,
  cx,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { GraphNode } from "@/lib/types";

export function NewJourneyDialog({
  projectId,
  open,
  onOpenChange,
  onCreated,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (journeyId: string) => void;
}) {
  const toast = useWorkspace((s) => s.toast);
  const queryClient = useQueryClient();

  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [chosen, setChosen] = React.useState<string[]>([]);
  const [formError, setFormError] = React.useState("");

  const operations = useQuery({
    queryKey: ["graph-operations", projectId],
    queryFn: () => api.graph(projectId, { level: 3, max_nodes: 1200 }),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const byId = React.useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const node of operations.data?.nodes ?? []) {
      if (node.type === "APIOperation") map.set(node.id, node);
    }
    return map;
  }, [operations.data]);

  const candidates = React.useMemo(() => {
    const query = search.trim().toLowerCase();
    const all = [...byId.values()].sort((a, b) => a.id.localeCompare(b.id));
    if (!query) return all;
    return all.filter(
      (node) =>
        node.label.toLowerCase().includes(query) ||
        node.id.toLowerCase().includes(query) ||
        String(node.attrs?.service ?? "").toLowerCase().includes(query),
    );
  }, [byId, search]);

  const reset = () => {
    setName("");
    setDescription("");
    setSearch("");
    setChosen([]);
    setFormError("");
  };

  const create = useMutation({
    mutationFn: () =>
      api.createJourney(projectId, {
        name: name.trim(),
        description: description.trim(),
        steps: chosen.map((operationId) => ({ operation_id: operationId })),
      }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["journeys", projectId] });
      toast("success", `Created “${result.journey.name}”.`);
      onCreated(result.journey.id);
      onOpenChange(false);
      reset();
    },
    onError: (error) => {
      const problem = error as ApiError;
      setFormError(
        problem.correlationId
          ? `${problem.message} (correlation ID ${problem.correlationId})`
          : problem.message,
      );
    },
  });

  const submit = () => {
    setFormError("");
    if (!name.trim()) {
      setFormError("Give the journey a name.");
      return;
    }
    if (chosen.length === 0) {
      setFormError("Add at least one operation.");
      return;
    }
    create.mutate();
  };

  const move = (position: number, delta: number) => {
    setChosen((current) => {
      const next = [...current];
      const target = position + delta;
      if (target < 0 || target >= next.length) return current;
      [next[position], next[target]] = [next[target], next[position]];
      return next;
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        onOpenChange(value);
        if (!value) reset();
      }}
      title="New journey"
      description="Pick the operations this flow calls, in the order it calls them."
      wide
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" loading={create.isPending} onClick={submit}>
            Create journey
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Refund an order"
            />
          </Field>
          <Field label="Description" hint="Optional. One sentence a non-engineer would understand.">
            <Input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="A shopper asks for their money back."
            />
          </Field>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {/* ------------------------------------------------- pick from here */}
          <div className="min-w-0">
            <p className="label-eyebrow mb-2">Available operations</p>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter by path, method or service"
              aria-label="Filter operations"
            />
            <div className="mt-2 max-h-[280px] overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--color-line)]">
              {operations.isLoading ? (
                <div className="p-3">
                  <LoadingBlock label="Loading operations" rows={4} />
                </div>
              ) : operations.error ? (
                <div className="p-3">
                  <ErrorState
                    detail={(operations.error as ApiError).message}
                    correlationId={(operations.error as ApiError).correlationId}
                    onRetry={() => void operations.refetch()}
                  />
                </div>
              ) : candidates.length === 0 ? (
                <p className="px-3 py-4 text-[12.5px] text-[var(--color-dim)]">
                  No operation matches “{search}”.
                </p>
              ) : (
                <ul className="divide-y divide-[var(--color-line)]">
                  {candidates.map((node) => {
                    const already = chosen.includes(node.id);
                    return (
                      <li key={node.id}>
                        <button
                          onClick={() => setChosen((current) => [...current, node.id])}
                          disabled={already}
                          className={cx(
                            "flex w-full items-center gap-2 px-3 py-2 text-left transition-colors duration-150",
                            already
                              ? "opacity-45"
                              : "hover:bg-[var(--color-surface-2)]",
                          )}
                        >
                          <Plus size={12} className="shrink-0 text-[var(--color-dim)]" aria-hidden />
                          <span className="min-w-0 flex-1">
                            <span className="mono block truncate text-[12px] text-[var(--color-ink)]">
                              {node.label}
                            </span>
                            <span className="block truncate text-[11px] text-[var(--color-dim)]">
                              {String(node.attrs?.service ?? "")}
                              {already ? " · already added" : ""}
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          {/* -------------------------------------------------- ordered steps */}
          <div className="min-w-0">
            <p className="label-eyebrow mb-2">Steps, in call order</p>
            <div className="max-h-[332px] overflow-y-auto rounded-[var(--radius-sm)] border border-[var(--color-line)]">
              {chosen.length === 0 ? (
                <p className="px-3 py-4 text-[12.5px] text-[var(--color-dim)]">
                  Nothing picked yet. Add operations from the left in the order they are
                  called.
                </p>
              ) : (
                <ol className="divide-y divide-[var(--color-line)]">
                  {chosen.map((operationId, position) => {
                    const node = byId.get(operationId);
                    return (
                      <li key={`${operationId}-${position}`} className="flex items-center gap-2 px-2.5 py-2">
                        <span className="numeral w-5 shrink-0 text-[11.5px] text-[var(--color-dim)]">
                          {position + 1}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="mono block truncate text-[12px] text-[var(--color-ink)]">
                            {node?.label ?? operationId}
                          </span>
                          <span className="block truncate text-[11px] text-[var(--color-dim)]">
                            {String(node?.attrs?.service ?? "")}
                          </span>
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Move step ${position + 1} earlier`}
                          disabled={position === 0}
                          onClick={() => move(position, -1)}
                        >
                          <ArrowUp size={12} aria-hidden />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Move step ${position + 1} later`}
                          disabled={position === chosen.length - 1}
                          onClick={() => move(position, 1)}
                        >
                          <ArrowDown size={12} aria-hidden />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Remove step ${position + 1}`}
                          onClick={() =>
                            setChosen((current) => current.filter((_, i) => i !== position))
                          }
                        >
                          <X size={12} aria-hidden />
                        </Button>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
          </div>
        </div>

        <InfoNote>
          A journey you compose here is recorded as your edit. It never becomes a
          specification fact, and it can be deleted again at any time.
        </InfoNote>

        {formError && (
          <p role="alert" className="text-[12.5px] text-[var(--color-broken)]">
            {formError}
          </p>
        )}
      </div>
    </Dialog>
  );
}
