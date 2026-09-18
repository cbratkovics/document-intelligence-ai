"use client";

import { useState } from "react";
import { countMatches, flowText, highlight } from "@/lib/highlight";
import type { Chunk, Hit, RetrievalMode, SearchResponse } from "@/lib/types";
import { BACKEND_TO_MODE } from "@/lib/types";
import type { ApiFailure } from "@/lib/api";

export interface EvidenceProps {
  question: string | null;
  results: SearchResponse | null;
  loading: boolean;
  failure: ApiFailure | null;
  latencyMs: number | null;
  mode: RetrievalMode;
  onModeChange: (mode: RetrievalMode) => void;
  rerank: boolean;
  rerankAvailable: boolean;
  onRerankChange: (value: boolean) => void;
  waking: boolean;
  wakingSeconds: number;
  onRetry: () => void;
  loadContext: (hit: Hit) => Promise<Chunk[]>;
  terms: string[];
}

const MODES: Array<{ value: RetrievalMode; label: string }> = [
  { value: "bm25", label: "BM25 only" },
  { value: "dense", label: "Dense only" },
  { value: "hybrid", label: "Hybrid" },
];

function locationLabel(hit: Hit): string {
  const parts: string[] = [];
  const loc = hit.location;
  if (loc.page != null) parts.push(loc.page_end && loc.page_end !== loc.page ? `pages ${loc.page}-${loc.page_end}` : `page ${loc.page}`);
  if (loc.section) parts.push(loc.section);
  parts.push(`chars ${loc.char_start}-${loc.char_end}`);
  return parts.join(" · ");
}

function Bar({ value, max, label }: { value: number | null; max: number; label: string }) {
  if (value == null || max <= 0) return <div className="bar-track" aria-hidden />;
  const pct = Math.max(2, Math.min(100, (value / max) * 100));
  return (
    <div className="bar-track" role="img" aria-label={`${label} ${value.toFixed(3)}`} title={`${label} ${value.toFixed(4)}`}>
      <div className="bar-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

function RankCell({
  rank,
  score,
  max,
  ran,
  label,
  poolSize,
  digits = 3,
}: {
  rank: number | null;
  score: number | null;
  max: number;
  ran: boolean;
  label: string;
  poolSize: number;
  digits?: number;
}) {
  if (!ran) {
    return (
      <div className="flex flex-col gap-1">
        <span className="text-xs text-ink-3">not run</span>
        <div className="bar-track" aria-hidden />
      </div>
    );
  }
  if (rank == null) {
    return (
      <div className="flex flex-col gap-1" title={`Not among the top ${poolSize} ${label} candidates`}>
        <span className="text-xs text-ink-3">outside top {poolSize}</span>
        <div className="bar-track" aria-hidden />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs tnum">
        <span className="font-semibold text-ink">#{rank}</span>
        {score != null && <span className="text-ink-3"> · {score.toFixed(digits)}</span>}
      </span>
      <Bar value={score} max={max} label={label} />
    </div>
  );
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden>
      <div className="rounded-md border border-line bg-surface p-4">
        <div className="skeleton mb-3 h-4 w-1/3" />
        <div className="skeleton mb-2 h-4 w-full" />
        <div className="skeleton mb-2 h-4 w-11/12" />
        <div className="skeleton h-4 w-2/3" />
      </div>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-[72px] rounded-md border border-line bg-surface p-3">
          <div className="skeleton mb-2 h-3 w-1/4" />
          <div className="skeleton h-3 w-3/4" />
        </div>
      ))}
    </div>
  );
}

function HitRow({
  hit,
  maxima,
  ran,
  poolSize,
  terms,
  rerankApplied,
  loadContext,
}: {
  hit: Hit;
  maxima: { lexical: number; vector: number; fusion: number; rerank: number };
  ran: { lexical: boolean; vector: boolean; fusion: boolean };
  poolSize: number;
  terms: string[];
  rerankApplied: boolean;
  loadContext: (hit: Hit) => Promise<Chunk[]>;
}) {
  const [open, setOpen] = useState(false);
  const [context, setContext] = useState<Chunk[] | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const panelId = `hit-${hit.chunk_id.replace(/[^a-z0-9]/gi, "")}`;
  const s = hit.scores;
  const matches = countMatches(hit.text, terms);

  async function showContext() {
    setContextLoading(true);
    setContextError(null);
    try {
      setContext(await loadContext(hit));
    } catch (error) {
      setContextError(error instanceof Error ? error.message : "Could not load context");
    } finally {
      setContextLoading(false);
    }
  }

  return (
    <li className="rounded-md border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="grid w-full grid-cols-[2rem_1fr] gap-x-3 gap-y-2 px-3 py-3 text-left sm:grid-cols-[2rem_minmax(0,1fr)_repeat(3,6.5rem)] sm:items-center"
      >
        <span className="text-sm font-semibold tnum text-ink">{hit.rank}</span>
        <span className="min-w-0">
          <span className="block truncate text-xs text-ink-2">
            <span className="font-medium text-ink">{hit.filename}</span> · {locationLabel(hit)}
            {matches > 0 && <span className="text-ink-3"> · {matches} term match{matches === 1 ? "" : "es"}</span>}
          </span>
          <span className="block truncate text-sm">{hit.text.replace(/\s+/g, " ").slice(0, 160)}</span>
        </span>
        <div className="col-span-2 grid grid-cols-3 gap-3 sm:col-span-3 sm:contents">
          <RankCell rank={s.lexical_rank} score={s.lexical_score} max={maxima.lexical} ran={ran.lexical} label="BM25" poolSize={poolSize} digits={2} />
          <RankCell rank={s.vector_rank} score={s.vector_similarity} max={maxima.vector} ran={ran.vector} label="dense" poolSize={poolSize} />
          <RankCell rank={s.fusion_rank} score={s.fusion_score} max={maxima.fusion} ran={ran.fusion} label="fused" poolSize={poolSize} digits={4} />
        </div>
      </button>
      <div id={panelId} hidden={!open} className="border-t border-line px-3 py-3">
        {rerankApplied && (
          <p className="mb-2 text-xs text-ink-2 tnum">
            Rerank score {s.rerank_score?.toFixed(3) ?? "n/a"} (heuristic term overlap); final position {hit.rank}
            {s.fusion_rank != null && s.fusion_rank !== hit.rank && `, was #${s.fusion_rank} after fusion`}.
          </p>
        )}
        <p className="whitespace-pre-wrap text-sm leading-6">{highlight(flowText(hit.text), terms)}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {context === null && (
            <button
              type="button"
              onClick={() => void showContext()}
              disabled={contextLoading}
              className="h-8 rounded-md border border-line px-3 text-xs font-medium hover:border-accent disabled:opacity-50"
            >
              {contextLoading ? "Loading context" : "Show in context"}
            </button>
          )}
          {contextError && <span className="text-xs text-bad">{contextError}</span>}
        </div>
        {context && (
          <ol className="mt-3 flex flex-col gap-2 border-l-2 border-line pl-3">
            {context.map((chunk) => (
              <li
                key={chunk.chunk_id}
                className={`rounded px-2 py-1 text-sm leading-6 ${
                  chunk.chunk_id === hit.chunk_id ? "bg-accent-soft" : "text-ink-2"
                }`}
              >
                <span className="block text-xs text-ink-3 tnum">
                  chunk {chunk.ordinal}
                  {chunk.location.section ? ` · ${chunk.location.section}` : ""}
                </span>
                <span className="whitespace-pre-wrap">
                  {chunk.chunk_id === hit.chunk_id ? highlight(flowText(chunk.text), terms) : flowText(chunk.text)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </li>
  );
}

export default function Evidence(props: EvidenceProps) {
  const { question, results, loading, failure, latencyMs, mode, onModeChange, rerank, rerankAvailable, onRerankChange, waking, wakingSeconds, onRetry, loadContext, terms } = props;

  const effective = results ? BACKEND_TO_MODE[results.mode_effective] : mode;
  const ran = {
    lexical: effective === "bm25" || effective === "hybrid",
    vector: effective === "dense" || effective === "hybrid",
    fusion: effective === "hybrid",
  };
  const hits = results?.results ?? [];
  const maxima = {
    lexical: Math.max(0, ...hits.map((h) => h.scores.lexical_score ?? 0)),
    vector: Math.max(0, ...hits.map((h) => h.scores.vector_similarity ?? 0)),
    fusion: Math.max(0, ...hits.map((h) => h.scores.fusion_score ?? 0)),
    rerank: Math.max(0, ...hits.map((h) => h.scores.rerank_score ?? 0)),
  };
  const top = hits[0];
  const rerankApplied = results?.rerank_status === "applied";

  return (
    <section aria-labelledby="evidence-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="evidence-heading" className="text-base font-semibold">
          Evidence
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <div role="radiogroup" aria-label="Retrieval mode" className="inline-flex rounded-md border border-line bg-surface p-0.5">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={mode === m.value}
                onClick={() => onModeChange(m.value)}
                className={`h-8 rounded px-3 text-xs font-medium ${
                  mode === m.value ? "bg-accent text-accent-ink" : "text-ink-2 hover:text-ink"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <label className={`inline-flex h-8 items-center gap-2 text-xs ${rerankAvailable ? "" : "opacity-50"}`}>
            <input
              type="checkbox"
              checked={rerank}
              disabled={!rerankAvailable}
              onChange={(e) => onRerankChange(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            Rerank (heuristic)
          </label>
        </div>
      </div>

      {waking ? (
        <div className="rounded-md border border-line bg-surface p-6 text-sm" role="status" aria-live="polite">
          <p className="font-medium">Waking the demo server, about 30 seconds.</p>
          <p className="mt-1 text-ink-2">
            The API sleeps when idle on the free tier. Waiting {wakingSeconds}s; this page retries on its own.
          </p>
          <button type="button" onClick={onRetry} className="mt-3 h-8 rounded-md border border-line px-3 text-xs font-medium hover:border-accent">
            Retry now
          </button>
        </div>
      ) : loading ? (
        <Skeleton />
      ) : failure ? (
        <div className="rounded-md border border-line bg-surface p-6 text-sm" role="alert">
          {failure.kind === "rate_limited" ? (
            <>
              <p className="font-medium">Rate limited.</p>
              <p className="mt-1 text-ink-2">
                The demo allows a limited number of requests per minute. Try again in {failure.retryAfter ?? 60} seconds.
              </p>
            </>
          ) : failure.kind === "unreachable" ? (
            <>
              <p className="font-medium">The demo server did not respond.</p>
              <p className="mt-1 text-ink-2">{failure.message}</p>
            </>
          ) : (
            <>
              <p className="font-medium">The request failed.</p>
              <p className="mt-1 text-ink-2">{failure.message}</p>
            </>
          )}
          <button type="button" onClick={onRetry} className="mt-3 h-8 rounded-md border border-line px-3 text-xs font-medium hover:border-accent">
            Retry
          </button>
        </div>
      ) : !results ? (
        <div className="rounded-md border border-dashed border-line p-6 text-sm text-ink-2">
          Ask a question or pick an example. Results show each passage with the rank it received from BM25, from the
          dense model, and after fusion, so you can see where the two retrievers disagree.
        </div>
      ) : hits.length === 0 ? (
        <div className="rounded-md border border-line bg-surface p-6 text-sm" role="status">
          <p className="font-medium">No passages retrieved.</p>
          <p className="mt-1 text-ink-2">
            {effective === "bm25"
              ? "None of the query terms appear in the documents in scope. Try dense or hybrid mode, which match meaning rather than exact words."
              : "Nothing in the documents in scope matched. Try rephrasing, or add a document."}
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-ink-2">
            <span>
              Ran <span className="font-medium text-ink">{MODES.find((m) => m.value === effective)?.label}</span>
              {results.mode_requested !== results.mode_effective && " (requested mode unavailable)"}
              {rerankApplied && ", then reranked"}
              {results.rerank_status === "failed" && ", rerank failed so fused order kept"}
              . Top {hits.length} of {results.candidate_k} candidates per branch.
            </span>
            {latencyMs != null && (
              <span className="tnum">
                {Math.round(latencyMs)} ms round trip
                {results.timings_ms.lexical_ms != null && ` · BM25 ${results.timings_ms.lexical_ms.toFixed(0)} ms`}
                {results.timings_ms.vector_ms != null && ` · dense ${results.timings_ms.vector_ms.toFixed(0)} ms`}
                {results.timings_ms.embed_query_ms != null && ` · embed ${results.timings_ms.embed_query_ms.toFixed(0)} ms`}
              </span>
            )}
          </div>

          {top && (
            <article className="rounded-md border-2 border-accent bg-surface p-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-accent">Top passage</p>
              <p className="mb-2 text-xs text-ink-2">
                <span className="font-medium text-ink">{top.filename}</span> · {locationLabel(top)}
              </p>
              <p className="whitespace-pre-wrap text-[15px] leading-7">{highlight(flowText(top.text), terms)}</p>
              <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-line pt-3 text-xs">
                {[
                  { label: "BM25 rank", value: ran.lexical ? top.scores.lexical_rank : null, ranBranch: ran.lexical },
                  { label: "Dense rank", value: ran.vector ? top.scores.vector_rank : null, ranBranch: ran.vector },
                  { label: "Fused rank", value: ran.fusion ? top.scores.fusion_rank : null, ranBranch: ran.fusion },
                ].map((cell) => (
                  <div key={cell.label}>
                    <dt className="text-ink-3">{cell.label}</dt>
                    <dd className="text-base font-semibold tnum">
                      {!cell.ranBranch ? <span className="text-sm font-normal text-ink-3">not run</span> : cell.value ?? <span className="text-sm font-normal text-ink-3">outside top {results.candidate_k}</span>}
                    </dd>
                  </div>
                ))}
              </dl>
            </article>
          )}

          <div className="hidden grid-cols-[2rem_minmax(0,1fr)_repeat(3,6.5rem)] gap-x-3 px-3 text-xs font-semibold uppercase tracking-wide text-ink-3 sm:grid">
            <span>#</span>
            <span>Passage</span>
            <span>BM25</span>
            <span>Dense</span>
            <span>Fused</span>
          </div>
          <ol className="flex flex-col gap-2" aria-label="Ranked passages">
            {hits.map((hit) => (
              <HitRow
                key={hit.chunk_id}
                hit={hit}
                maxima={maxima}
                ran={ran}
                poolSize={results.candidate_k}
                terms={terms}
                rerankApplied={Boolean(rerankApplied)}
                loadContext={loadContext}
              />
            ))}
          </ol>
          <p className="text-xs text-ink-3">
            Bars are scaled to the best score in this result set. BM25 scores, cosine similarities and fusion scores
            are separate quantities and are not comparable with each other or across queries. A branch rank is shown
            only when the pipeline computed it.
            {question && terms.length === 0 && " This question contains only stopwords, so BM25 has nothing to match."}
          </p>
          {results.notes.length > 0 && (
            <ul className="text-xs text-warn">
              {results.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
