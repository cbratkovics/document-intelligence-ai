import { clientIp, errorResponse, jsonNoStore, relayError, upstream } from "@/lib/upstream";
import { MODE_TO_BACKEND, type RetrievalMode } from "@/lib/types";

export const dynamic = "force-dynamic";

const MAX_QUERY_CHARS = 2000;
const TOP_K = 8;
const ID_RE = /^[a-f0-9]{32}$/;

interface SearchBody {
  text?: unknown;
  mode?: unknown;
  doc_ids?: unknown;
  use_reranker?: unknown;
}

export async function POST(request: Request) {
  let body: SearchBody;
  try {
    body = await request.json();
  } catch {
    return jsonNoStore({ error: "Body must be JSON", code: "invalid_request" }, 400);
  }
  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (!text) return jsonNoStore({ error: "Enter a question", code: "invalid_request" }, 400);
  if (text.length > MAX_QUERY_CHARS) {
    return jsonNoStore(
      { error: `Questions are limited to ${MAX_QUERY_CHARS} characters`, code: "invalid_request" },
      400,
    );
  }
  const mode = (typeof body.mode === "string" ? body.mode : "hybrid") as RetrievalMode;
  if (!(mode in MODE_TO_BACKEND)) {
    return jsonNoStore({ error: "Unknown retrieval mode", code: "invalid_request" }, 400);
  }
  // The client always scopes to seeded documents plus its own uploads. An
  // empty scope is forwarded as-is and matches nothing, by design.
  const docIds = Array.isArray(body.doc_ids)
    ? Array.from(new Set(body.doc_ids.filter((v) => typeof v === "string" && ID_RE.test(v))))
    : [];
  if (docIds.length > 50) {
    return jsonNoStore({ error: "Too many documents in scope", code: "invalid_request" }, 400);
  }

  try {
    const response = await upstream("/api/v1/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        mode: MODE_TO_BACKEND[mode],
        top_k: TOP_K,
        doc_ids: docIds,
        use_reranker: body.use_reranker === true,
      }),
      clientIp: clientIp(request),
      timeoutMs: 30_000,
    });
    if (!response.ok) return relayError(response);
    return jsonNoStore(await response.json());
  } catch (error) {
    return errorResponse(error);
  }
}
