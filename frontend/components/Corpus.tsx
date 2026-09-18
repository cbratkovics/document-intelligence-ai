"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { CHIPS } from "@/lib/chips";
import type { DocumentRecord } from "@/lib/types";

export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;
export const ALLOWED = [".txt", ".md", ".rst", ".pdf"];

interface Props {
  documents: DocumentRecord[];
  question: string;
  onQuestionChange: (value: string) => void;
  onAsk: (question: string) => void;
  /** Example chips always run in hybrid mode so all three rank columns are filled. */
  onChip: (question: string) => void;
  onUpload: (file: File) => Promise<void>;
  uploadProgress: number | null;
  uploadMessage: { tone: "ok" | "bad" | "warn"; text: string } | null;
  disabled: boolean;
}

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index === -1 ? "" : name.slice(index).toLowerCase();
}

export function validateFile(file: File): string | null {
  const ext = extensionOf(file.name);
  if (!ALLOWED.includes(ext)) {
    return `"${file.name}" is not a supported type. Allowed: ${ALLOWED.join(", ")}.`;
  }
  if (file.size === 0) return `"${file.name}" is empty.`;
  if (file.size > MAX_UPLOAD_BYTES) {
    return `"${file.name}" is ${(file.size / 1_048_576).toFixed(1)} MB; the limit is 4 MB.`;
  }
  return null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export default function Corpus({
  documents,
  question,
  onQuestionChange,
  onAsk,
  onChip,
  onUpload,
  uploadProgress,
  uploadMessage,
  disabled,
}: Props) {
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    const problem = validateFile(file);
    if (problem) {
      setLocalError(problem);
      return;
    }
    setLocalError(null);
    await onUpload(file);
    if (inputRef.current) inputRef.current.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void handleFiles(event.dataTransfer.files);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim()) onAsk(question.trim());
  }

  const seeded = documents.filter((d) => d.seeded);
  const own = documents.filter((d) => !d.seeded);
  const uploading = uploadProgress !== null;

  return (
    <div className="flex flex-col gap-5">
      <section aria-labelledby="ask-heading">
        <h2 id="ask-heading" className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
          Ask a question
        </h2>
        <form onSubmit={submit} className="flex flex-col gap-2">
          <label htmlFor="question" className="sr-only">
            Question
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => onQuestionChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (question.trim() && !disabled) onAsk(question.trim());
              }
            }}
            rows={2}
            maxLength={2000}
            placeholder="Ask about the sample documents, or upload your own"
            className="w-full resize-y rounded-md border border-line bg-surface px-3 py-2 text-sm leading-6 placeholder:text-ink-3"
          />
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-ink-3">Enter to search, Shift+Enter for a new line</span>
            <button
              type="submit"
              disabled={disabled || !question.trim()}
              className="h-9 rounded-md bg-accent px-4 text-sm font-medium text-accent-ink disabled:opacity-50"
            >
              Search
            </button>
          </div>
        </form>
      </section>

      <section aria-labelledby="chips-heading">
        <h2 id="chips-heading" className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
          Try one of these
        </h2>
        <ul className="flex flex-col gap-1.5">
          {CHIPS.map((chip) => (
            <li key={chip.text}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChip(chip.text)}
                className="w-full rounded-md border border-line bg-surface px-3 py-2 text-left hover:border-accent disabled:opacity-50"
              >
                <span className="block text-sm leading-5">{chip.text}</span>
                <span className="block text-xs text-ink-3">{chip.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="docs-heading">
        <h2 id="docs-heading" className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
          Documents in scope
        </h2>
        <ul className="divide-y divide-line rounded-md border border-line bg-surface">
          {documents.length === 0 && <li className="px-3 py-3 text-sm text-ink-3">No documents loaded yet.</li>}
          {[...seeded, ...own].map((doc) => (
            <li key={doc.doc_id} className="flex items-baseline justify-between gap-3 px-3 py-2">
              <span className="min-w-0 truncate text-sm" title={doc.filename}>
                {doc.filename}
              </span>
              <span className="shrink-0 text-xs text-ink-3 tnum">
                {doc.seeded ? "sample" : "yours"} · {doc.chunk_count} chunks · {formatSize(doc.size_bytes)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="upload-heading">
        <h2 id="upload-heading" className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
          Add a document
        </h2>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled && !uploading) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`rounded-md border border-dashed px-3 py-4 text-center ${
            dragging ? "border-accent bg-accent-soft" : "border-line bg-surface"
          }`}
        >
          <label className="block cursor-pointer text-sm">
            <span className="font-medium text-accent">Choose a file</span>
            <span className="text-ink-2"> or drop it here</span>
            <input
              ref={inputRef}
              type="file"
              accept={ALLOWED.join(",")}
              disabled={disabled || uploading}
              onChange={(e) => void handleFiles(e.target.files)}
              className="sr-only"
            />
          </label>
          <p className="mt-1 text-xs text-ink-3">PDF, TXT, MD or RST, up to 4 MB</p>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-track" aria-hidden={!uploading}>
            <div
              className="h-full bg-accent transition-[width] duration-200"
              style={{ width: `${uploading ? Math.round((uploadProgress ?? 0) * 100) : 0}%` }}
            />
          </div>
          <div className="min-h-10 pt-2 text-left text-xs" role="status" aria-live="polite">
            {localError ? (
              <span className="text-bad">{localError}</span>
            ) : uploadMessage ? (
              <span className={uploadMessage.tone === "bad" ? "text-bad" : uploadMessage.tone === "warn" ? "text-warn" : "text-ok"}>
                {uploadMessage.text}
              </span>
            ) : (
              <span className="text-ink-3">
                Uploads are temporary and this is a public demo. Do not upload anything sensitive.
              </span>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
