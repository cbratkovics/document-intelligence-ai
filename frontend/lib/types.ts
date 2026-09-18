// Shapes exchanged between the browser, the Next.js route handlers, and the
// FastAPI service. Field names mirror the backend so nothing is renamed twice.

export type RetrievalMode = "bm25" | "dense" | "hybrid";
export type BackendMode = "lexical" | "vector" | "hybrid";

export const MODE_TO_BACKEND: Record<RetrievalMode, BackendMode> = {
  bm25: "lexical",
  dense: "vector",
  hybrid: "hybrid",
};

export const BACKEND_TO_MODE: Record<BackendMode, RetrievalMode> = {
  lexical: "bm25",
  vector: "dense",
  hybrid: "hybrid",
};

export interface Health {
  status: "ok" | "degraded" | "unreachable";
  retrieval_mode: "hybrid" | "lexical";
  embedding_provider: string;
  embedding_model: string | null;
  embedding_semantic: boolean;
  reranker_mode: string;
  generation_provider: string;
  generation_available: boolean;
  document_count: number | null;
  seeded_doc_ids: string[];
  seed_errors: string[];
  supported_extensions: string[];
  max_upload_size: number;
  startup_error: string | null;
}

export interface Location {
  char_start: number;
  char_end: number;
  page: number | null;
  page_end: number | null;
  section: string | null;
}

export interface Scores {
  vector_distance: number | null;
  vector_similarity: number | null;
  vector_rank: number | null;
  lexical_score: number | null;
  lexical_rank: number | null;
  fusion_score: number | null;
  fusion_rank: number | null;
  rerank_score: number | null;
}

export interface Hit {
  chunk_id: string;
  doc_id: string;
  version: number;
  ordinal: number;
  filename: string;
  text: string;
  location: Location;
  scores: Scores;
  rank: number;
}

export interface SearchResponse {
  query: string;
  results: Hit[];
  total: number;
  mode_requested: BackendMode;
  mode_effective: BackendMode;
  rerank_status: "applied" | "disabled" | "unavailable" | "failed";
  reranker: string | null;
  candidate_k: number;
  /** What each branch actually returned; null for a branch that did not run. Absent on older APIs. */
  candidates_returned?: { lexical: number | null; vector: number | null };
  timings_ms: Record<string, number>;
  notes: string[];
}

export interface DocumentRecord {
  doc_id: string;
  filename: string;
  status: string;
  chunk_count: number;
  page_count: number | null;
  size_bytes: number;
  created_at: string;
  seeded: boolean;
}

export interface Chunk {
  chunk_id: string;
  ordinal: number;
  text: string;
  location: Location;
}

export interface ChunksResponse {
  doc_id: string;
  chunk_count: number;
  offset: number;
  limit: number;
  chunks: Chunk[];
}

export interface UploadResponse {
  document: DocumentRecord;
  created: boolean;
  duplicate_of: string | null;
  warnings: string[];
  evicted: string[];
}

export interface ApiError {
  error: string;
  code: string | null;
  retry_after?: number;
}
