import type { Health } from "@/lib/types";

const GITHUB = "https://github.com/cbratkovics/document-intelligence-ai";

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "accent" | "warn" }) {
  const cls =
    tone === "accent"
      ? "border-accent text-accent"
      : tone === "warn"
        ? "border-warn text-warn"
        : "border-line text-ink-2";
  return (
    <span className={`inline-flex h-7 items-center rounded-md border px-2 text-xs font-medium whitespace-nowrap ${cls}`}>
      {children}
    </span>
  );
}

export function modeLabel(health: Health): string {
  if (health.retrieval_mode !== "hybrid") return "BM25 only";
  const model = (health.embedding_model || "").split("/").pop() || health.embedding_provider;
  return `Hybrid: BM25 + ${model.replace("all-MiniLM-L6-v2", "MiniLM-L6")}`;
}

export default function Header({ health, waking }: { health: Health | null; waking: boolean }) {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Document Intelligence</h1>
            <p className="text-sm text-ink-2">
              Hybrid document retrieval that shows its evidence: every passage carries its BM25, dense and fused ranks.
            </p>
          </div>
          <a
            href={GITHUB}
            className="text-sm font-medium text-accent underline-offset-4 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            Source on GitHub
          </a>
        </div>
        <div className="flex min-h-7 flex-wrap items-center gap-2" aria-live="polite">
          {health ? (
            <>
              <Badge tone="accent">{modeLabel(health)}</Badge>
              <Badge>
                Reranker: {health.reranker_mode === "none" ? "none" : `${health.reranker_mode} (on request)`}
              </Badge>
              <Badge>Generation: {health.generation_provider === "none" ? "off" : health.generation_provider}</Badge>
              <Badge>
                {health.document_count ?? 0} document{health.document_count === 1 ? "" : "s"} indexed
              </Badge>
              {health.status !== "ok" && <Badge tone="warn">Server degraded</Badge>}
            </>
          ) : (
            <Badge tone={waking ? "warn" : "neutral"}>{waking ? "Waking the demo server" : "Checking server"}</Badge>
          )}
          <span className="text-xs text-ink-3">Retrieval-only demo. No LLM is called.</span>
        </div>
      </div>
    </header>
  );
}
