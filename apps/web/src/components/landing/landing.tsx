"use client";

/**
 * The landing page.
 *
 * Editorial rather than promotional: one clear promise, one clear action, and a short
 * scrollytelling sequence that shows the six verbs the product is built around. No
 * scroll hijacking — the sequence is driven by an IntersectionObserver, so the page
 * scrolls exactly as fast as the reader wants it to.
 */

import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Boxes,
  Cpu,
  Download,
  GitBranch,
  Lock,
  MessageSquareText,
  Play,
  Search,
  ShieldCheck,
  Wrench,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { GalaxyField } from "@/components/landing/galaxy-field";
import { Badge, Button, Card } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";

const CHAPTERS = [
  {
    id: "explore",
    verb: "Explore",
    icon: Search,
    headline: "It organises itself before you ask.",
    body:
      "Seven specifications land as seven business domains, not seven files. Start at " +
      "capabilities, zoom to services and journeys, then to endpoints, schemas and fields " +
      "— only when you want them.",
    detail: "Semantic zoom · 4 levels · stable colours and shapes",
  },
  {
    id: "ask",
    verb: "Ask",
    icon: MessageSquareText,
    headline: "Ask in English. Get the graph, not a paragraph.",
    body:
      "“How does checkout work?” lights the actual path through cart, order, inventory and " +
      "payment, with a citation on every hop. The model may only reference nodes that exist " +
      "— anything it invents is discarded before you see it.",
    detail: "Grounded answers · evidence per hop · fact and inference kept apart",
  },
  {
    id: "break",
    verb: "Break",
    icon: Zap,
    headline: "Rename a field. Watch the blast radius.",
    body:
      "Break Lab clones the graph and calculates impact deterministically: broken, degraded, " +
      "potentially affected, unaffected — with the dependency chain that explains each one, " +
      "and the journeys that stop working.",
    detail: "Never mutates the source · undo, reset, compare",
  },
  {
    id: "repair",
    verb: "Repair",
    icon: Wrench,
    headline: "Fix it, then prove it is fixed.",
    body:
      "Take a deterministic repair or a proposed one, edit it, apply it, and replay the " +
      "journey. “Journey restored” only appears after validation actually passes.",
    detail: "Patch summary · migration checklist · replayed, not assumed",
  },
  {
    id: "compare",
    verb: "Compare",
    icon: Cpu,
    headline: "Two models, one task, one schema.",
    body:
      "Send the same bounded context to Ollama and Kimi and compare what they found: " +
      "agreement, disagreement, invented references, latency and cost. You decide which " +
      "answer becomes part of the model, and the decision is logged.",
    detail: "Model Arena · immutable decision log",
  },
  {
    id: "export",
    verb: "Export",
    icon: Download,
    headline: "Share the result without shipping the app.",
    body:
      "A self-contained interactive HTML report that opens from a file, with search, " +
      "pan-and-zoom, an inspector and journey playback. Plus PDF, SVG, PNG, Mermaid, " +
      "JSON-LD, GraphML, CSV and Markdown.",
    detail: "No CDN · no backend · no API key",
  },
] as const;

export function Landing() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const openDemo = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.createDemo();
      router.push(`/workspace/${result.project_id}`);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not open the demo estate. Is the backend running?",
      );
      setLoading(false);
    }
  }, [router]);

  return (
    <main id="main">
      {/* ------------------------------------------------------------- hero */}
      <section className="relative flex min-h-[100svh] flex-col overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <GalaxyField className="absolute inset-0 h-full w-full" />
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 90% 60% at 50% 42%, transparent 20%, var(--color-base) 78%)",
            }}
          />
        </div>

        <header className="relative z-10 flex items-center justify-between px-6 py-5 sm:px-10">
          <div className="flex items-center gap-2.5">
            <GalaxyMark />
            <span className="text-[14px] font-semibold tracking-tight">API Galaxy</span>
          </div>
          <nav className="flex items-center gap-2">
            <Link
              href="/import"
              className="rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] text-[var(--color-ink-2)] transition-colors hover:text-[var(--color-ink)]"
            >
              Import
            </Link>
            <a
              href="https://github.com"
              className="hidden rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] text-[var(--color-ink-2)] transition-colors hover:text-[var(--color-ink)] sm:block"
            >
              Source
            </a>
          </nav>
        </header>

        <div className="relative z-10 mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-6 text-center">
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          >
            <Badge tone="accent" className="mb-6" icon={<Lock size={11} aria-hidden />}>
              Local-first · Ollama by default · no account
            </Badge>

            <h1 className="text-balance text-[clamp(2.6rem,7vw,4.75rem)] font-semibold leading-[0.98] tracking-[-0.035em]">
              Your API,
              <br />
              <span className="bg-gradient-to-r from-[var(--color-ink)] via-[var(--color-accent-soft)] to-[var(--color-cyan)] bg-clip-text text-transparent">
                as a living model.
              </span>
            </h1>

            <p className="mx-auto mt-6 max-w-xl text-pretty text-[15px] leading-relaxed text-[var(--color-muted)] sm:text-[16px]">
              Drop your API. Watch it come alive. Ask how it works.
              <br className="hidden sm:block" /> Break it before production does.
            </p>

            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button size="lg" variant="primary" onClick={openDemo} loading={loading}>
                {loading ? "Assembling the galaxy" : "Explore the demo galaxy"}
                {!loading && <ArrowRight size={15} aria-hidden />}
              </Button>
              <Button size="lg" variant="secondary" onClick={() => router.push("/import")}>
                Import your API
              </Button>
            </div>

            {error && (
              <p role="alert" className="mt-4 text-[13px] text-[var(--color-broken)]">
                {error}
              </p>
            )}

            <p className="mt-6 text-[12px] text-[var(--color-dim)]">
              The demo needs nothing installed — no model, no key, no internet.
            </p>
          </motion.div>
        </div>

        <div className="relative z-10 mx-auto w-full max-w-5xl px-6 pb-10">
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-line)] sm:grid-cols-4">
            {[
              { value: "7", label: "services" },
              { value: "32", label: "operations" },
              { value: "366", label: "graph nodes" },
              { value: "15", label: "findings" },
            ].map((stat) => (
              <div key={stat.label} className="bg-[var(--color-base)]/85 px-4 py-4 text-center backdrop-blur">
                <div className="numeral text-[22px] font-semibold text-[var(--color-ink)]">
                  {stat.value}
                </div>
                <div className="mt-0.5 text-[11.5px] text-[var(--color-dim)]">{stat.label}</div>
              </div>
            ))}
          </div>
          <p className="mt-2.5 text-center text-[11.5px] text-[var(--color-dim)]">
            The bundled NovaCart estate, parsed deterministically in under a second.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------- what it is not */}
      <section className="mx-auto max-w-5xl px-6 py-24">
        <p className="label-eyebrow">The difference</p>
        <h2 className="mt-3 max-w-3xl text-balance text-[clamp(1.6rem,3.6vw,2.4rem)] font-semibold leading-tight tracking-[-0.028em]">
          A chat assistant can summarise your spec file. It cannot show you what breaks.
        </h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {[
            {
              icon: Boxes,
              title: "A model, not a message",
              body:
                "A persistent graph you navigate, filter and export — not a paragraph that " +
                "disappears when you close the tab.",
            },
            {
              icon: ShieldCheck,
              title: "Evidence, not vibes",
              body:
                "Every node, edge, finding and answer records the file and JSON Pointer it " +
                "came from. Facts and inferences never merge.",
            },
            {
              icon: GitBranch,
              title: "Consequences, computed",
              body:
                "Change impact is graph traversal, not a guess. The same input always " +
                "produces the same blast radius.",
            },
          ].map((item) => (
            <Card key={item.title} className="p-5">
              <item.icon size={17} className="text-[var(--color-accent-soft)]" aria-hidden />
              <h3 className="mt-3 text-[14px] font-semibold text-[var(--color-ink)]">
                {item.title}
              </h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--color-muted)]">
                {item.body}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------ scrollytelling */}
      <section className="mx-auto max-w-5xl px-6 pb-8">
        <p className="label-eyebrow">The loop</p>
        <h2 className="mt-3 text-[clamp(1.6rem,3.6vw,2.4rem)] font-semibold tracking-[-0.028em]">
          Drop → Explore → Ask → Break → Repair → Export
        </h2>
      </section>

      <div className="mx-auto max-w-5xl px-6 pb-24">
        {CHAPTERS.map((chapter, index) => (
          <Chapter key={chapter.id} chapter={chapter} index={index} reduce={!!reduce} />
        ))}
      </div>

      {/* ---------------------------------------------------------- privacy */}
      <section className="border-t border-[var(--color-line)] bg-[var(--color-surface)]/40">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <div className="grid gap-10 md:grid-cols-[1.1fr_1fr]">
            <div>
              <p className="label-eyebrow">Privacy</p>
              <h2 className="mt-3 text-balance text-[clamp(1.5rem,3.2vw,2.1rem)] font-semibold leading-tight tracking-[-0.028em]">
                Nothing leaves this machine unless you say so — and you see what would go.
              </h2>
              <p className="mt-4 max-w-lg text-[13.5px] leading-relaxed text-[var(--color-muted)]">
                Ollama is the default and the app is fully useful with no model at all.
                The optional external provider is off until you add a key, and even then
                every project needs its own consent. Before the first request you get a
                preview of the exact payload, with credentials, emails, phone numbers,
                internal URLs and example values already stripped out.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <Badge tone="fact">Deterministic parse</Badge>
                <Badge tone="inferred">Labelled inference</Badge>
                <Badge tone="user">Your decisions, logged</Badge>
              </div>
            </div>
            <Card className="overflow-hidden p-0">
              <div className="border-b border-[var(--color-line)] px-4 py-2.5 text-[11.5px] font-medium text-[var(--color-dim)]">
                Sanitised before sending
              </div>
              <pre className="scroll-x mono p-4 text-[11.5px] leading-relaxed text-[var(--color-ink-2)]">
{`- "contact": "ops@novacart.example"
+ "contact": "[REDACTED_EMAIL]"
- "server":  "http://10.0.0.5:8080"
+ "server":  "[REDACTED_INTERNAL_URL]"
- "token":   "sk-9f2a…"
+ "token":   "[REDACTED_SECRET]"

  dropped 12 example values
  dropped 14 server declarations`}
              </pre>
            </Card>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- close */}
      <section className="mx-auto max-w-3xl px-6 py-24 text-center">
        <h2 className="text-balance text-[clamp(1.7rem,4vw,2.5rem)] font-semibold tracking-[-0.03em]">
          Sixty seconds to understand an API estate you have never seen.
        </h2>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button size="lg" variant="primary" onClick={openDemo} loading={loading}>
            <Play size={14} aria-hidden />
            Explore the demo galaxy
          </Button>
          <Button size="lg" variant="ghost" onClick={() => router.push("/import")}>
            Import your own
          </Button>
        </div>
      </section>

      <footer className="border-t border-[var(--color-line)]">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-2 px-6 py-8 text-center">
          <div className="flex items-center gap-2">
            <GalaxyMark small />
            <span className="text-[13px] font-medium">API Galaxy</span>
          </div>
          <p className="text-[12.5px] font-medium text-[var(--color-ink-2)]">The Sunday Builds</p>
          <p className="text-[12px] text-[var(--color-dim)]">
            Solving Real Problems Using Free AI, Every Sunday!
          </p>
        </div>
      </footer>
    </main>
  );
}

function Chapter({
  chapter,
  index,
  reduce,
}: {
  chapter: (typeof CHAPTERS)[number];
  index: number;
  reduce: boolean;
}) {
  const Icon = chapter.icon;
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 26 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-12% 0px -12% 0px" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="grid gap-6 border-t border-[var(--color-line)] py-12 md:grid-cols-[180px_1fr]"
    >
      <div className="flex items-start gap-3">
        <span className="numeral mt-[3px] text-[12px] text-[var(--color-dim)]">
          {String(index + 1).padStart(2, "0")}
        </span>
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-[var(--color-accent-soft)]" aria-hidden />
          <span className="text-[14px] font-semibold tracking-tight">{chapter.verb}</span>
        </div>
      </div>
      <div className="max-w-2xl">
        <h3 className="text-balance text-[clamp(1.15rem,2.4vw,1.55rem)] font-semibold leading-snug tracking-[-0.022em]">
          {chapter.headline}
        </h3>
        <p className="mt-3 text-[13.5px] leading-relaxed text-[var(--color-muted)]">
          {chapter.body}
        </p>
        <p className="mono mt-3 text-[11.5px] text-[var(--color-dim)]">{chapter.detail}</p>
      </div>
    </motion.div>
  );
}

function GalaxyMark({ small }: { small?: boolean }) {
  const size = small ? 16 : 20;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="2.6" fill="var(--color-accent)" />
      <ellipse
        cx="12"
        cy="12"
        rx="10"
        ry="4.2"
        stroke="var(--color-cyan)"
        strokeOpacity="0.75"
        strokeWidth="1.1"
        transform="rotate(-28 12 12)"
      />
      <ellipse
        cx="12"
        cy="12"
        rx="10"
        ry="4.2"
        stroke="var(--color-violet)"
        strokeOpacity="0.5"
        strokeWidth="1.1"
        transform="rotate(34 12 12)"
      />
      <circle cx="20.4" cy="8.2" r="1.15" fill="var(--color-cyan)" />
      <circle cx="4.1" cy="15.4" r="0.95" fill="var(--color-violet)" />
    </svg>
  );
}
