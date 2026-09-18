"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Header from "@/components/Header";
import Corpus from "@/components/Corpus";
import Evidence from "@/components/Evidence";
import { ApiFailure, getChunks, getDocuments, getHealth, search, uploadFile } from "@/lib/api";
import { queryTerms } from "@/lib/highlight";
import { readOwnDocIds, writeOwnDocIds } from "@/lib/session";
import type { Chunk, DocumentRecord, Health, Hit, RetrievalMode, SearchResponse } from "@/lib/types";

const WAKE_BACKOFF_MS = [1500, 2500, 4000, 6000, 8000, 10000];
const WAKE_GIVE_UP_MS = 4 * 60 * 1000;

export default function Demo() {
  const [health, setHealth] = useState<Health | null>(null);
  const [waking, setWaking] = useState(false);
  const [wakingSeconds, setWakingSeconds] = useState(0);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [ownIds, setOwnIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [rerank, setRerank] = useState(false);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadMessage, setUploadMessage] = useState<{ tone: "ok" | "bad" | "warn"; text: string } | null>(null);
  const inflight = useRef<AbortController | null>(null);
  const wakeToken = useRef(0);
  const runSearchRef = useRef<
    ((text: string, mode: RetrievalMode, rerank: boolean, docIds?: string[]) => Promise<void>) | null
  >(null);

  const refreshDocuments = useCallback(async (own: string[]) => {
    try {
      const data = await getDocuments(own);
      setDocuments(data.documents);
      // Drop ids the server no longer has (evicted or restarted).
      const alive = new Set(data.documents.map((d) => d.doc_id));
      const kept = own.filter((id) => alive.has(id));
      if (kept.length !== own.length) {
        setOwnIds(kept);
        writeOwnDocIds(kept);
      }
    } catch {
      // Health polling surfaces connectivity problems; keep the last list.
    }
  }, []);

  /** Poll /api/health with backoff until the server answers; used at start and on failure. */
  const wake = useCallback(async () => {
    const token = ++wakeToken.current;
    const started = Date.now();
    let attempt = 0;
    for (;;) {
      if (token !== wakeToken.current) return;
      try {
        const h = await getHealth();
        if (token !== wakeToken.current) return;
        setHealth(h);
        setWaking(false);
        const own = readOwnDocIds();
        setOwnIds(own);
        await refreshDocuments(own);
        // Shareable links: /?q=...&mode=bm25|dense|hybrid runs on load.
        const params = new URLSearchParams(window.location.search);
        const q = (params.get("q") || "").trim().slice(0, 2000);
        const m = params.get("mode");
        const initialMode: RetrievalMode = m === "bm25" || m === "dense" || m === "hybrid" ? m : "hybrid";
        if (q) {
          setMode(initialMode);
          void runSearchRef.current?.(q, initialMode, false, [...h.seeded_doc_ids, ...own]);
        }
        return;
      } catch {
        if (token !== wakeToken.current) return;
        const elapsed = Date.now() - started;
        setWaking(true);
        setWakingSeconds(Math.round(elapsed / 1000));
        if (elapsed > WAKE_GIVE_UP_MS) {
          setFailure(new ApiFailure("unreachable", "The demo server did not wake up in four minutes.", 503));
          setWaking(false);
          return;
        }
        const delay = WAKE_BACKOFF_MS[Math.min(attempt, WAKE_BACKOFF_MS.length - 1)];
        attempt += 1;
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  }, [refreshDocuments]);

  useEffect(() => {
    // Deferred so the effect body itself sets no state; wake() only sets
    // state after network responses arrive.
    const timer = setTimeout(() => void wake(), 0);
    return () => {
      clearTimeout(timer);
      wakeToken.current += 1;
    };
  }, [wake]);

  const scope = useCallback(() => {
    const seeded = health?.seeded_doc_ids ?? [];
    return Array.from(new Set([...seeded, ...ownIds]));
  }, [health, ownIds]);

  const runSearch = useCallback(
    async (text: string, nextMode: RetrievalMode, nextRerank: boolean, docIds?: string[]) => {
      inflight.current?.abort();
      const controller = new AbortController();
      inflight.current = controller;
      setAsked(text);
      setQuestion(text);
      setLoading(true);
      setFailure(null);
      const started = performance.now();
      try {
        const data = await search(text, nextMode, docIds ?? scope(), nextRerank, controller.signal);
        if (controller.signal.aborted) return;
        setResults(data);
        setLatencyMs(performance.now() - started);
      } catch (error) {
        if (controller.signal.aborted) return;
        const f = error instanceof ApiFailure ? error : new ApiFailure("api", "Unexpected error", 0);
        setFailure(f);
        if (f.kind === "unreachable") {
          setHealth(null);
          void wake();
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    },
    [scope, wake],
  );

  runSearchRef.current = runSearch;

  function onAsk(text: string) {
    void runSearch(text, mode, rerank);
  }

  function onChip(text: string) {
    // Chips are the first thing most visitors click: show BM25, dense and
    // fused ranks together regardless of a mode picked earlier.
    setMode("hybrid");
    void runSearch(text, "hybrid", rerank);
  }

  function onModeChange(next: RetrievalMode) {
    setMode(next);
    if (asked) void runSearch(asked, next, rerank);
  }

  function onRerankChange(next: boolean) {
    setRerank(next);
    if (asked) void runSearch(asked, mode, next);
  }

  async function onUpload(file: File) {
    setUploadMessage(null);
    setUploadProgress(0);
    try {
      const data = await uploadFile(file, setUploadProgress);
      const id = data.document.doc_id;
      const own = Array.from(new Set([...ownIds, id]));
      setOwnIds(own);
      writeOwnDocIds(own);
      await refreshDocuments(own);
      try {
        setHealth(await getHealth());
      } catch {
        // keep the previous header state
      }
      const notes: string[] = [];
      if (!data.created) notes.push("identical content was already indexed, so it was reused");
      if (data.evicted.length) notes.push(`${data.evicted.length} older upload${data.evicted.length === 1 ? " was" : "s were"} evicted to stay within the corpus cap`);
      if (data.warnings.length) notes.push(data.warnings.join("; "));
      setUploadMessage({
        tone: notes.length ? "warn" : "ok",
        text: `Indexed ${data.document.filename} (${data.document.chunk_count} chunks)${notes.length ? `. Note: ${notes.join(". ")}.` : "."}`,
      });
    } catch (error) {
      const f = error instanceof ApiFailure ? error : null;
      setUploadMessage({
        tone: "bad",
        text: f?.kind === "rate_limited" ? `Rate limited; try again in ${f.retryAfter ?? 60} seconds.` : f?.message || "Upload failed.",
      });
      if (f?.kind === "unreachable") {
        setHealth(null);
        void wake();
      }
    } finally {
      setUploadProgress(null);
    }
  }

  async function loadContext(hit: Hit): Promise<Chunk[]> {
    const offset = Math.max(0, hit.ordinal - 1);
    const data = await getChunks(hit.doc_id, offset, 3, ownIds);
    return data.chunks;
  }

  const ready = health !== null && !waking;
  const terms = asked ? queryTerms(asked) : [];

  return (
    <div className="flex min-h-full flex-col">
      <Header health={health} waking={waking} />
      <main className="mx-auto grid w-full max-w-6xl flex-1 grid-cols-1 gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
        <Corpus
          documents={documents}
          question={question}
          onQuestionChange={setQuestion}
          onAsk={onAsk}
          onChip={onChip}
          onUpload={onUpload}
          uploadProgress={uploadProgress}
          uploadMessage={uploadMessage}
          disabled={!ready}
        />
        <Evidence
          question={asked}
          results={results}
          loading={loading}
          failure={failure}
          latencyMs={latencyMs}
          mode={mode}
          onModeChange={onModeChange}
          rerank={rerank}
          rerankAvailable={Boolean(health && health.reranker_mode !== "none")}
          onRerankChange={onRerankChange}
          waking={waking}
          wakingSeconds={wakingSeconds}
          onRetry={() => {
            setFailure(null);
            if (!health) void wake();
            else if (asked) void runSearch(asked, mode, rerank);
          }}
          loadContext={loadContext}
          terms={terms}
        />
      </main>
      <footer className="border-t border-line px-4 py-4 text-center text-xs text-ink-3">
        Sample documents describe a fictional company. Uploads are temporary, visible only to this browser session,
        and evicted oldest-first when the corpus cap is reached.
      </footer>
    </div>
  );
}
