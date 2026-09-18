"use client";

/**
 * Ask — a question in English, an answer in graph.
 *
 * The contract with the reader is that an answer is never just prose: it arrives with the
 * subgraph it came from, a citation per claim, and a visible separation between what the
 * specification says and what something inferred.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { CornerDownLeft, MessageSquareText, Sparkles } from "lucide-react";
import { useParams } from "next/navigation";
import * as React from "react";
import { AnswerPanel } from "@/components/ask/answer-panel";
import { ConsentDialog } from "@/components/ask/consent-dialog";
import { ContextPreviewCard } from "@/components/ask/context-preview";
import { ProviderPicker, type ProviderKind } from "@/components/ask/provider-picker";
import { QuestionHistory, type HistoryEntry } from "@/components/ask/question-history";
import { GraphCanvas, GraphNodeList } from "@/components/graph/graph-canvas";
import { Inspector } from "@/components/workspace/inspector";
import { InspectorRail, PageHeader } from "@/components/workspace/shell";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingBlock,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { useWorkspace } from "@/lib/store";
import type { Answer, GraphEdge, GraphNode } from "@/lib/types";

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();
  const scenarioId = useWorkspace((s) => s.activeScenarioId);
  const setHighlight = useWorkspace((s) => s.setHighlight);
  const clearHighlight = useWorkspace((s) => s.clearHighlight);
  const select = useWorkspace((s) => s.select);
  const toast = useWorkspace((s) => s.toast);

  const [question, setQuestion] = React.useState("");
  const [provider, setProvider] = React.useState<ProviderKind>("deterministic");
  const [answer, setAnswer] = React.useState<Answer | null>(null);
  const [history, setHistory] = React.useState<HistoryEntry[]>([]);
  const [consentOpen, setConsentOpen] = React.useState(false);
  const [consentGranted, setConsentGranted] = React.useState(false);
  const [consentPending, setConsentPending] = React.useState(false);

  const starters = useQuery({
    queryKey: ["starters", projectId],
    queryFn: () => api.starters(projectId),
  });

  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.providers(),
    staleTime: 30_000,
  });

  // Level 4 rather than 3: answers about aliases and conflicting definitions cite fields,
  // which only exist at the deepest level. Measured on the demo estate this is 366 nodes,
  // so the extra depth costs nothing and the alternative is an empty canvas.
  const graph = useQuery({
    queryKey: ["graph-l4", projectId, scenarioId],
    queryFn: () =>
      api.graph(projectId, { level: 4, max_nodes: 1400, scenario: scenarioId ?? undefined }),
    staleTime: 5 * 60 * 1000,
  });

  React.useEffect(() => () => clearHighlight(), [clearHighlight]);

  const ask = useMutation({
    mutationFn: (payload: { question: string; provider: ProviderKind }) =>
      api.ask(projectId, {
        question: payload.question,
        provider: payload.provider,
        scenario_id: scenarioId,
      }),
    onSuccess: (result) => {
      setAnswer(result);
      setHighlight({
        nodes: result.highlighted_node_ids,
        edges: result.highlighted_edge_ids,
        path: result.path,
        reason: result.question,
      });
      setHistory((current) =>
        [
          {
            id: `${Date.now()}-${Math.random()}`,
            question: result.question,
            provider: result.provider,
            grounded: result.grounded,
            confidence: result.confidence,
            at: Date.now(),
          },
          ...current.filter((entry) => entry.question !== result.question),
        ].slice(0, 12),
      );
      setConsentPending(false);
    },
    onError: (error) => {
      setConsentPending(false);
      const problem = error as ApiError;
      // 428 is the backend refusing to make an external call without explicit consent.
      if (problem.needsConsent) {
        setConsentOpen(true);
        return;
      }
      toast(
        "error",
        problem.correlationId
          ? `${problem.message} (correlation ID ${problem.correlationId})`
          : problem.message,
      );
    },
  });

  const submit = React.useCallback(
    (text: string, kind: ProviderKind) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setQuestion(trimmed);
      // Anything leaving this machine is previewed and approved before it is sent.
      if (kind === "kimi" && !consentGranted) {
        setProvider("kimi");
        setConsentOpen(true);
        return;
      }
      ask.mutate({ question: trimmed, provider: kind });
    },
    [ask, consentGranted],
  );

  const approveConsent = async () => {
    setConsentPending(true);
    try {
      await api.setConsent(projectId, true);
      setConsentGranted(true);
      setConsentOpen(false);
      ask.mutate({ question: question.trim(), provider: "kimi" });
    } catch (error) {
      setConsentPending(false);
      const problem = error as ApiError;
      toast("error", `Consent could not be recorded: ${problem.message}`);
    }
  };

  // The answer's own subgraph: only the nodes it cited, and the edges between them.
  const subgraph = React.useMemo<{ nodes: GraphNode[]; edges: GraphEdge[] }>(() => {
    if (!graph.data || !answer) return { nodes: [], edges: [] };
    const wanted = new Set([...answer.highlighted_node_ids, ...answer.path]);
    const nodes = graph.data.nodes.filter((node) => wanted.has(node.id));
    const present = new Set(nodes.map((node) => node.id));
    const edges = graph.data.edges.filter(
      (edge) => present.has(edge.source) && present.has(edge.target),
    );
    return { nodes, edges };
  }, [graph.data, answer]);

  const starterChips = starters.data?.starters ?? [];

  return (
    <>
      <div className="flex h-full min-h-0">
        <div className="flex min-w-0 flex-1 flex-col">
          <PageHeader
            icon={MessageSquareText}
            title="Ask"
            subtitle="Questions are answered from the graph, with a citation on every claim. The default engine uses no model at all, so it cannot invent anything."
          />

          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            <div className="mx-auto max-w-[1220px] space-y-4">
              {/* ------------------------------------------------- composer */}
              <Card className="p-4">
                <label
                  htmlFor="ask-question"
                  className="label-eyebrow mb-1.5 block"
                >
                  Your question
                </label>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <textarea
                    id="ask-question"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        submit(question, provider);
                      }
                    }}
                    rows={2}
                    placeholder="How does checkout work?"
                    className="min-h-[58px] w-full resize-y rounded-[var(--radius-sm)] border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-3 py-2.5 text-[15px] leading-relaxed text-[var(--color-ink)] placeholder:text-[var(--color-dim)] transition-colors duration-150 focus:border-[var(--color-accent)]"
                  />
                  <Button
                    variant="primary"
                    size="lg"
                    className="shrink-0"
                    loading={ask.isPending}
                    disabled={!question.trim()}
                    onClick={() => submit(question, provider)}
                  >
                    Ask <CornerDownLeft size={13} aria-hidden />
                  </Button>
                </div>
                <p className="mt-1.5 text-[11.5px] text-[var(--color-dim)]">
                  Enter to ask · Shift + Enter for a new line
                </p>

                {starterChips.length > 0 && (
                  <div className="mt-3">
                    <p className="label-eyebrow mb-1.5">Try one of these</p>
                    <ul className="flex flex-wrap gap-1.5">
                      {starterChips.map((starter) => (
                        <li key={starter}>
                          <button
                            onClick={() => submit(starter, provider)}
                            className="flex items-center gap-1.5 rounded-full border border-[var(--color-line-strong)] bg-[var(--color-surface-2)] px-2.5 py-1 text-[12px] text-[var(--color-ink-2)] transition-colors duration-150 hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
                          >
                            <Sparkles size={11} className="text-[var(--color-dim)]" aria-hidden />
                            {starter}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="mt-4 border-t border-[var(--color-line)] pt-3.5">
                  <ProviderPicker
                    value={provider}
                    onChange={setProvider}
                    providers={providers.data?.providers ?? []}
                    loading={providers.isLoading}
                  />
                </div>
              </Card>

              {/* --------------------------------------- answer beside graph */}
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(310px,0.72fr)]">
                <div className="min-w-0">
                  {ask.isPending ? (
                    <Card className="p-5">
                      <LoadingBlock label="Answering from the graph" rows={6} />
                    </Card>
                  ) : ask.error && !(ask.error as ApiError).needsConsent ? (
                    <ErrorState
                      title="The question could not be answered"
                      detail={(ask.error as ApiError).message}
                      hint={(ask.error as ApiError).hint}
                      correlationId={(ask.error as ApiError).correlationId}
                      onRetry={() => submit(question, provider)}
                    />
                  ) : answer ? (
                    <AnswerPanel answer={answer} onSelectNode={select} />
                  ) : (
                    <Card>
                      <EmptyState
                        icon={<MessageSquareText size={22} aria-hidden />}
                        title="Nothing asked yet"
                        body="Type a question above, or pick one of the starters. Every answer arrives with its evidence and the part of the graph it came from."
                      />
                    </Card>
                  )}
                </div>

                <div className="min-w-0 space-y-3">
                  <Card className="overflow-hidden">
                    <div className="flex items-center justify-between gap-2 border-b border-[var(--color-line)] px-3.5 py-2.5">
                      <p className="label-eyebrow">The part of the graph it used</p>
                      <span className="numeral text-[11px] text-[var(--color-dim)]">
                        {subgraph.nodes.length} nodes
                      </span>
                    </div>
                    {graph.isLoading ? (
                      <div className="p-4">
                        <LoadingBlock label="Loading the graph" rows={4} />
                      </div>
                    ) : graph.error ? (
                      <div className="p-4">
                        <ErrorState
                          title="The graph could not be loaded"
                          detail={(graph.error as ApiError).message}
                          correlationId={(graph.error as ApiError).correlationId}
                          onRetry={() => void graph.refetch()}
                        />
                      </div>
                    ) : !answer || subgraph.nodes.length === 0 ? (
                      <p className="px-3.5 py-6 text-center text-[12.5px] text-[var(--color-dim)]">
                        {answer
                          ? "This answer cited nothing that exists at this graph level."
                          : "Ask a question and the nodes behind the answer light up here."}
                      </p>
                    ) : (
                      <>
                        <GraphCanvas
                          nodes={subgraph.nodes}
                          edges={subgraph.edges}
                          highlightNodes={answer.highlighted_node_ids}
                          highlightEdges={answer.highlighted_edge_ids}
                          pathNodes={answer.path}
                          onSelectNode={(nodeId) => nodeId && select(nodeId)}
                          className="h-[300px] w-full"
                          ariaLabel={`The subgraph behind the answer to “${answer.question}”: ${subgraph.nodes.length} nodes. The list below is the keyboard equivalent.`}
                        />
                        <div className="max-h-[220px] overflow-y-auto border-t border-[var(--color-line)]">
                          <GraphNodeList nodes={subgraph.nodes} onSelect={select} />
                        </div>
                      </>
                    )}
                  </Card>

                  <ContextPreviewCard projectId={projectId} question={question} />

                  <QuestionHistory
                    entries={history}
                    onRerun={(entry) => submit(entry.question, provider)}
                    onClear={() => setHistory([])}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <InspectorRail>
          <Inspector projectId={projectId} />
        </InspectorRail>
      </div>

      <ConsentDialog
        projectId={projectId}
        question={question}
        open={consentOpen}
        onOpenChange={setConsentOpen}
        onApprove={() => void approveConsent()}
        sending={consentPending || ask.isPending}
      />
    </>
  );
}
