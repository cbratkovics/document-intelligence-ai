import { clientIp, errorResponse, jsonNoStore, relayError, upstream } from "@/lib/upstream";

export const dynamic = "force-dynamic";

export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;
export const ALLOWED_EXTENSIONS = [".txt", ".md", ".rst", ".pdf"];

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index === -1 ? "" : name.slice(index).toLowerCase();
}

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return jsonNoStore({ error: "Expected a multipart upload", code: "invalid_request" }, 400);
  }
  const file = form.get("file");
  if (!(file instanceof File)) {
    return jsonNoStore({ error: "Choose a file to upload", code: "invalid_request" }, 400);
  }
  const extension = extensionOf(file.name);
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return jsonNoStore(
      {
        error: `Unsupported file type "${extension || "none"}". Allowed: ${ALLOWED_EXTENSIONS.join(", ")}`,
        code: "unsupported_type",
      },
      400,
    );
  }
  if (file.size === 0) {
    return jsonNoStore({ error: "The file is empty", code: "empty_file" }, 400);
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return jsonNoStore(
      { error: `Files are limited to 4 MB (this one is ${(file.size / 1_048_576).toFixed(1)} MB)`, code: "too_large" },
      413,
    );
  }

  const outbound = new FormData();
  outbound.append("file", file, file.name);
  try {
    const response = await upstream("/api/v1/documents/upload", {
      method: "POST",
      body: outbound,
      clientIp: clientIp(request),
      timeoutMs: 60_000,
    });
    if (!response.ok) return relayError(response);
    const data = await response.json();
    const doc = data.document || {};
    return jsonNoStore({
      document: {
        doc_id: doc.doc_id,
        filename: doc.filename,
        status: doc.status,
        chunk_count: doc.chunk_count,
        page_count: doc.page_count ?? null,
        size_bytes: doc.size_bytes,
        created_at: doc.created_at,
        seeded: false,
      },
      created: Boolean(data.created),
      duplicate_of: data.duplicate_of ?? null,
      warnings: Array.isArray(data.warnings) ? data.warnings : [],
      evicted: Array.isArray(data.evicted) ? data.evicted : [],
    });
  } catch (error) {
    return errorResponse(error);
  }
}
