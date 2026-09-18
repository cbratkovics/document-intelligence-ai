import {
  clientIp,
  errorResponse,
  isValidId,
  jsonNoStore,
  parseIdList,
  relayError,
  seededDocIds,
  upstream,
} from "@/lib/upstream";

export const dynamic = "force-dynamic";

// Expand-in-context: neighbouring chunks of one document. Only seeded
// documents and ids the browser declares as its own can be read.
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isValidId(id)) return jsonNoStore({ error: "Unknown document", code: "not_found" }, 404);
  const url = new URL(request.url);
  const own = parseIdList(url.searchParams.get("own"));
  const offset = Math.max(0, Number(url.searchParams.get("offset") || 0) | 0);
  const limit = Math.min(20, Math.max(1, Number(url.searchParams.get("limit") || 3) | 0));
  try {
    const seeded = await seededDocIds();
    if (!seeded.includes(id) && !own.includes(id)) {
      return jsonNoStore({ error: "Unknown document", code: "not_found" }, 404);
    }
    const response = await upstream(
      `/api/v1/documents/${id}/chunks?offset=${offset}&limit=${limit}`,
      { clientIp: clientIp(request), timeoutMs: 15_000 },
    );
    if (!response.ok) return relayError(response);
    const data = await response.json();
    return jsonNoStore({
      doc_id: data.doc_id,
      chunk_count: data.chunk_count,
      offset: data.offset,
      limit: data.limit,
      chunks: data.chunks,
    });
  } catch (error) {
    return errorResponse(error);
  }
}
