# ADR-0002: Use embedded ChromaDB for vector storage

## Status
Accepted (revised for 0.2.0)

## Context
The system needs a dense index for optional vector retrieval that runs
locally without an external service, supports metadata filtering by document
id, persists to disk, and lets the application supply its own embeddings.

## Decision
Use ChromaDB's embedded `PersistentClient` (or `EphemeralClient` in ephemeral
mode) with a collection created explicitly in cosine space. The application
always supplies embeddings; the collection has no embedding function, so
Chroma never downloads a model. The embedding identity is stored in the
collection metadata and checked at startup.

## Consequences
- Single-process, local deployment only; no Chroma server is required or
  configured.
- Cosine distance makes `1 - distance` a faithful similarity, which the
  default L2 space would not.
- Changing the embedding model requires deleting the index directory; the
  application refuses to mix identities.
- The manifest, not Chroma, is the source of truth for what is indexed.
