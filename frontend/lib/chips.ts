// Example questions over the seeded corpus. Each label states what the
// hybrid run's top passage actually scored (BM25 rank, dense rank, fused
// rank), so a visitor knows which retriever did the work. Re-check the labels
// whenever data/samples/ changes: they describe observed results, not intent.
export interface Chip {
  text: string;
  watch: "bm25" | "dense" | "hybrid";
  label: string;
}

export const CHIPS: Chip[] = [
  { text: "What does error code DQ-E417 mean?", watch: "bm25", label: "exact code: BM25 ranks it first, dense second" },
  { text: "What is JOB-7731?", watch: "hybrid", label: "exact identifier: both retrievers rank it first" },
  { text: "What counts as a returning customer?", watch: "dense", label: "paraphrase: dense ranks it first, BM25 finds no match" },
  { text: "Why did nobody notice the alert during the incident?", watch: "hybrid", label: "fusion: neither retriever ranks it first, rank fusion does" },
  { text: "Which action items came out of INC-2024-031?", watch: "hybrid", label: "identifier plus wording: both retrievers rank it first" },
  { text: "Where should business logic live in dbt models?", watch: "hybrid", label: "the document's own words: both retrievers rank it first" },
];
