import type { ReactNode } from "react";

// Same stopword list as the backend's BM25 tokenizer, so what we highlight is
// what the lexical branch could actually have matched.
const STOPWORDS = new Set(
  `a an and are as at be been by can could did do does for from had has have he her his how i if in
   into is it its may might of on or our shall she should that the their them then there these they
   this those to us was we were what when where which who whom why will with would you your`.split(/\s+/),
);

export function queryTerms(query: string): string[] {
  const terms = (query.toLowerCase().match(/[\p{L}\p{N}_]+/gu) || []).filter((t) => !STOPWORDS.has(t));
  return Array.from(new Set(terms));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Wrap whole-word matches of the query terms in <mark>. */
export function highlight(text: string, terms: string[]): ReactNode {
  if (!terms.length) return text;
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}_])(${terms.map(escapeRegExp).join("|")})(?![\\p{L}\\p{N}_])`, "giu");
  const parts: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) parts.push(text.slice(last, start));
    parts.push(<mark key={key++}>{match[0]}</mark>);
    last = start + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function countMatches(text: string, terms: string[]): number {
  if (!terms.length) return 0;
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}_])(${terms.map(escapeRegExp).join("|")})(?![\\p{L}\\p{N}_])`, "giu");
  return Array.from(text.matchAll(pattern)).length;
}

/**
 * Display-only reflow: join hard-wrapped lines into paragraphs while keeping
 * blank-line paragraph breaks, headings, list items and table rows on their
 * own lines. Offsets shown to the user still refer to the original text.
 */
export function flowText(text: string): string {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const out: string[] = [];
  for (const raw of lines) {
    const line = raw.trimEnd();
    const startsBlock = /^\s*([-*+]\s|\d+\.\s|#{1,6}\s|\||>)/.test(line);
    const prev = out.length ? out[out.length - 1] : "";
    if (line.trim() === "" || prev === "" || startsBlock || out.length === 0) {
      out.push(line.trim() === "" ? "" : line);
    } else {
      out[out.length - 1] = `${prev} ${line.trimStart()}`;
    }
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
