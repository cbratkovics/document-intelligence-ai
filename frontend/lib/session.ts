// Per-browser memory of what this visitor uploaded. sessionStorage is a
// convenience only: it can be empty or throw (private windows, cleared data),
// and the page must work without it.

const KEY = "docintel.ownDocIds";

export function readOwnDocIds(): string[] {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    const ids = raw ? JSON.parse(raw) : [];
    return Array.isArray(ids) ? ids.filter((v) => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function writeOwnDocIds(ids: string[]): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(Array.from(new Set(ids))));
  } catch {
    // Ignore: the list lives in React state for the rest of the session.
  }
}
