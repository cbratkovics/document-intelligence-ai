// Server-only helpers for talking to the FastAPI service. The API key never
// leaves this process: the browser only ever calls the /api/* route handlers.

import "server-only";

const DEFAULT_TIMEOUT_MS = 30_000;

export class UpstreamError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
  ) {
    super(message);
  }
}

function config(): { baseUrl: string; apiKey: string } {
  const baseUrl = (process.env.API_BASE_URL || "").replace(/\/+$/, "");
  const apiKey = process.env.API_KEY || "";
  if (!baseUrl) {
    throw new UpstreamError("API_BASE_URL is not configured", 500, "misconfigured");
  }
  return { baseUrl, apiKey };
}

/** First hop of the forwarded chain, as set by the hosting platform's proxy. */
export function clientIp(request: Request): string | null {
  const headers = request.headers;
  const candidates = [
    headers.get("x-vercel-forwarded-for"),
    headers.get("x-forwarded-for"),
    headers.get("x-real-ip"),
  ];
  for (const value of candidates) {
    const first = (value || "").split(",")[0].trim();
    if (first) return first.slice(0, 128);
  }
  return null;
}

export interface UpstreamOptions {
  method?: "GET" | "POST";
  body?: BodyInit | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  /** Health is the only route that must work without a key. */
  auth?: boolean;
  clientIp?: string | null;
}

/**
 * Call the service and return its Response. Network failures and timeouts
 * become UpstreamError(502/504) so callers can show a "server waking" state.
 */
export async function upstream(path: string, options: UpstreamOptions = {}): Promise<Response> {
  const { baseUrl, apiKey } = config();
  const headers: Record<string, string> = { ...(options.headers || {}) };
  if (options.auth !== false) {
    if (!apiKey) throw new UpstreamError("API_KEY is not configured", 500, "misconfigured");
    headers["X-API-Key"] = apiKey;
    if (options.clientIp) headers["X-Client-IP"] = options.clientIp;
  }
  try {
    return await fetch(`${baseUrl}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body ?? undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS),
    });
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    if (name === "TimeoutError" || name === "AbortError") {
      throw new UpstreamError("The demo server did not answer in time", 504, "upstream_timeout");
    }
    throw new UpstreamError("The demo server is unreachable", 502, "upstream_unreachable");
  }
}

/** Pass an upstream error body through with its status, sanitised to our shape. */
export async function relayError(response: Response): Promise<Response> {
  let body: { error?: string; code?: string | null; detail?: unknown } = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  const retryAfter = response.headers.get("retry-after");
  const payload = {
    error: body.error || `Request failed (${response.status})`,
    code: body.code ?? null,
    ...(retryAfter ? { retry_after: Number(retryAfter) } : {}),
  };
  const headers: Record<string, string> = { "Cache-Control": "no-store" };
  if (retryAfter) headers["Retry-After"] = retryAfter;
  return Response.json(payload, { status: response.status, headers });
}

export function errorResponse(error: unknown): Response {
  if (error instanceof UpstreamError) {
    return Response.json(
      { error: error.message, code: error.code },
      { status: error.status, headers: { "Cache-Control": "no-store" } },
    );
  }
  console.error("route handler failure", error);
  return Response.json(
    { error: "Internal error", code: "internal_error" },
    { status: 500, headers: { "Cache-Control": "no-store" } },
  );
}

export function jsonNoStore(data: unknown, status = 200): Response {
  return Response.json(data, { status, headers: { "Cache-Control": "no-store" } });
}

/** Seeded ids come from /health, which needs no key and is cheap. */
export async function seededDocIds(): Promise<string[]> {
  const response = await upstream("/health", { auth: false, timeoutMs: 10_000 });
  if (!response.ok) return [];
  const health = await response.json();
  return Array.isArray(health.seeded_doc_ids) ? health.seeded_doc_ids : [];
}

const ID_RE = /^[a-f0-9]{32}$/;

export function parseIdList(raw: string | null | undefined, max = 50): string[] {
  if (!raw) return [];
  const ids = raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => ID_RE.test(s));
  return Array.from(new Set(ids)).slice(0, max);
}

export function isValidId(id: string): boolean {
  return ID_RE.test(id);
}
