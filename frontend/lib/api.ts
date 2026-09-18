// Browser-side calls to this app's own route handlers. The Space is never
// called directly from the browser.

import type {
  ChunksResponse,
  DocumentRecord,
  Health,
  RetrievalMode,
  SearchResponse,
  UploadResponse,
} from "./types";

export type FailureKind = "unreachable" | "rate_limited" | "api";

export class ApiFailure extends Error {
  constructor(
    public readonly kind: FailureKind,
    message: string,
    public readonly status: number,
    public readonly code: string | null = null,
    public readonly retryAfter: number | null = null,
  ) {
    super(message);
  }
}

async function failureFrom(response: Response): Promise<ApiFailure> {
  let body: { error?: string; code?: string | null; retry_after?: number } = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  const message = body.error || `Request failed (${response.status})`;
  if (response.status === 429) {
    const retry = body.retry_after ?? Number(response.headers.get("retry-after") || 0);
    return new ApiFailure("rate_limited", message, 429, body.code ?? null, retry || null);
  }
  if (response.status === 502 || response.status === 503 || response.status === 504) {
    return new ApiFailure("unreachable", message, response.status, body.code ?? null);
  }
  return new ApiFailure("api", message, response.status, body.code ?? null);
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, { ...init, cache: "no-store" });
  } catch {
    throw new ApiFailure("unreachable", "Network error", 0);
  }
  if (!response.ok) throw await failureFrom(response);
  return (await response.json()) as T;
}

export function getHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export function getDocuments(ownIds: string[]): Promise<{ documents: DocumentRecord[]; seeded_doc_ids: string[] }> {
  const query = ownIds.length ? `?own=${encodeURIComponent(ownIds.join(","))}` : "";
  return request(`/api/documents${query}`);
}

export function search(
  text: string,
  mode: RetrievalMode,
  docIds: string[],
  useReranker: boolean,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, mode, doc_ids: docIds, use_reranker: useReranker }),
    signal,
  });
}

export function getChunks(docId: string, offset: number, limit: number, ownIds: string[]): Promise<ChunksResponse> {
  const own = ownIds.length ? `&own=${encodeURIComponent(ownIds.join(","))}` : "";
  return request<ChunksResponse>(`/api/documents/${docId}/chunks?offset=${offset}&limit=${limit}${own}`);
}

/** XMLHttpRequest so the browser can report upload progress. */
export function uploadFile(file: File, onProgress: (fraction: number) => void): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiFailure("unreachable", "Network error during upload", 0));
    xhr.onload = () => {
      let body: Record<string, unknown> = {};
      try {
        body = JSON.parse(xhr.responseText || "{}");
      } catch {
        body = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as unknown as UploadResponse);
        return;
      }
      const message = (body.error as string) || `Upload failed (${xhr.status})`;
      const code = (body.code as string | null) ?? null;
      if (xhr.status === 429) {
        reject(new ApiFailure("rate_limited", message, 429, code, (body.retry_after as number) || null));
      } else if (xhr.status >= 502 && xhr.status <= 504) {
        reject(new ApiFailure("unreachable", message, xhr.status, code));
      } else {
        reject(new ApiFailure("api", message, xhr.status, code));
      }
    };
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.send(form);
  });
}
