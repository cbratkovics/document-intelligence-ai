import { errorResponse, jsonNoStore, upstream } from "@/lib/upstream";
import type { Health } from "@/lib/types";

export const dynamic = "force-dynamic";

// Public, keyless. Reports what the deployed service actually runs so the UI
// can label itself truthfully. Upstream failures are reported as
// status "unreachable" with a 503 so the client can show the waking state.
export async function GET() {
  try {
    const response = await upstream("/health", { auth: false, timeoutMs: 12_000 });
    if (!response.ok) {
      return jsonNoStore({ status: "unreachable", http_status: response.status }, 503);
    }
    const raw = await response.json();
    const caps = raw.capabilities || {};
    const health: Health = {
      status: raw.status === "ok" ? "ok" : "degraded",
      retrieval_mode: raw.retrieval_mode === "hybrid" ? "hybrid" : "lexical",
      embedding_provider: String(raw.embedding_provider ?? "none"),
      embedding_model: raw.embedding_model ?? null,
      embedding_semantic: Boolean(raw.embedding_semantic),
      reranker_mode: String(raw.reranker_mode ?? "none"),
      generation_provider: String(raw.generation_provider ?? "none"),
      generation_available: Boolean(raw.generation_available),
      document_count: typeof raw.document_count === "number" ? raw.document_count : null,
      seeded_doc_ids: Array.isArray(raw.seeded_doc_ids) ? raw.seeded_doc_ids : [],
      seed_errors: Array.isArray(raw.seed_errors) ? raw.seed_errors : [],
      supported_extensions: Array.isArray(caps.supported_extensions)
        ? caps.supported_extensions
        : [],
      max_upload_size: typeof caps.max_upload_size === "number" ? caps.max_upload_size : 0,
      startup_error: raw.startup_error ?? null,
    };
    return jsonNoStore(health, health.status === "ok" ? 200 : 503);
  } catch (error) {
    // Unreachable or timed out: the Space is most likely asleep.
    const status = error instanceof Error && "status" in error ? 503 : 500;
    if (status === 503) return jsonNoStore({ status: "unreachable" }, 503);
    return errorResponse(error);
  }
}
