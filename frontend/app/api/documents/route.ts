import {
  clientIp,
  errorResponse,
  jsonNoStore,
  parseIdList,
  relayError,
  seededDocIds,
  upstream,
} from "@/lib/upstream";
import type { DocumentRecord } from "@/lib/types";

export const dynamic = "force-dynamic";

// Upload isolation: the service holds one shared corpus, so the list is
// filtered to the seeded samples plus whichever ids this browser says it
// uploaded (kept in its sessionStorage). Nobody sees anyone else's uploads.
export async function GET(request: Request) {
  const own = parseIdList(new URL(request.url).searchParams.get("own"));
  try {
    const [seeded, response] = await Promise.all([
      seededDocIds(),
      upstream("/api/v1/documents", { clientIp: clientIp(request), timeoutMs: 15_000 }),
    ]);
    if (!response.ok) return relayError(response);
    const all: Array<Record<string, unknown>> = await response.json();
    const seededSet = new Set(seeded);
    const ownSet = new Set(own);
    const visible: DocumentRecord[] = all
      .filter((d) => seededSet.has(String(d.doc_id)) || ownSet.has(String(d.doc_id)))
      .filter((d) => d.status === "ready")
      .map((d) => ({
        doc_id: String(d.doc_id),
        filename: String(d.filename),
        status: String(d.status),
        chunk_count: Number(d.chunk_count),
        page_count: (d.page_count as number | null) ?? null,
        size_bytes: Number(d.size_bytes),
        created_at: String(d.created_at),
        seeded: seededSet.has(String(d.doc_id)),
      }));
    return jsonNoStore({ documents: visible, seeded_doc_ids: seeded });
  } catch (error) {
    return errorResponse(error);
  }
}
