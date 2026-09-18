// Example questions over the seeded corpus. Each says what to watch, so a
// visitor knows which retriever the question is designed to favour.
export interface Chip {
  text: string;
  watch: "bm25" | "dense" | "hybrid";
  label: string;
}

export const CHIPS: Chip[] = [
  { text: "What does error code DQ-E417 mean?", watch: "bm25", label: "exact code: BM25 should lead" },
  { text: "What is JOB-7731?", watch: "bm25", label: "exact identifier: BM25 should lead" },
  { text: "What counts as a returning customer?", watch: "dense", label: "paraphrase: dense finds it, BM25 finds nothing" },
  { text: "Why did nobody notice the alert during the incident?", watch: "dense", label: "concept: dense should lead" },
  { text: "Which action items came out of INC-2024-031?", watch: "hybrid", label: "identifier plus concept: both contribute" },
  { text: "Where should business logic live in dbt models?", watch: "hybrid", label: "both retrievers agree" },
];
