/** Mirrors the server rules (FR-006); server errors stay authoritative. */
export const MAX_CHUNK_CHARS = 400;
export const PAUSE_MIN_MS = 100;
export const PAUSE_MAX_MS = 3000;

const BRACKET = /\[([^\]]*)\]/g;
const EMPHASIS = /\*[^*\s](?:[^*]*[^*\s])?\*/g;

export function validateChunkText(text: string): string[] {
  const errors: string[] = [];
  if (text.trim() === "") errors.push("Chunk text is empty.");
  if (text.length > MAX_CHUNK_CHARS) {
    errors.push(
      `Chunk has ${String(text.length)} characters; the limit is ${String(MAX_CHUNK_CHARS)}.`,
    );
  }
  for (const m of text.matchAll(BRACKET)) {
    const inner = m[1] ?? "";
    const pause = /^pause (\d+)$/.exec(inner);
    if (!pause) {
      errors.push(`Unknown marker [${inner}]. Allowed: [pause N] and *word*.`);
      continue;
    }
    const ms = Number(pause[1]);
    if (ms < PAUSE_MIN_MS || ms > PAUSE_MAX_MS) {
      errors.push(
        `Pause ${String(ms)} is out of range. Use ${String(PAUSE_MIN_MS)} to ${String(PAUSE_MAX_MS)}.`,
      );
    }
  }
  const rest = text.replace(BRACKET, "").replace(EMPHASIS, "");
  if (/[[\]]/.test(rest)) errors.push("Unclosed or stray bracket. Markers look like [pause 400].");
  if (rest.includes("*")) errors.push("Emphasis must look like *word*.");
  return errors;
}

export interface Edit {
  text: string;
  caret: number;
}

/** Insert a marker at the selection. Emphasis wraps the selected text. */
export function insertMarker(text: string, start: number, end: number, marker: string): Edit {
  if (marker === "*word*") {
    const selected = text.slice(start, end);
    const word = selected === "" ? "word" : selected;
    const wrapped = `*${word}*`;
    return {
      text: text.slice(0, start) + wrapped + text.slice(end),
      caret: start + wrapped.length,
    };
  }
  return { text: text.slice(0, start) + marker + text.slice(end), caret: start + marker.length };
}

export interface Suggestion {
  label: string;
  start: number;
  end: number;
}

/** Autocomplete for a partially typed `[p...` pause marker before the caret. */
export function markerSuggestion(text: string, caret: number): Suggestion | null {
  const before = text.slice(0, caret);
  const m = /\[p[a-z]*(?: (\d*))?$/.exec(before);
  if (!m) return null;
  const typed = m[0];
  let label: string;
  if (typed.startsWith("[pause ")) {
    const digits = m[1] ?? "";
    label = `[pause ${digits === "" ? "400" : digits}]`;
  } else if ("[pause".startsWith(typed)) {
    label = "[pause 400]";
  } else {
    return null;
  }
  const end = text[caret] === "]" ? caret + 1 : caret;
  return { label, start: caret - typed.length, end };
}

export function applySuggestion(text: string, s: Suggestion): Edit {
  return {
    text: text.slice(0, s.start) + s.label + text.slice(s.end),
    caret: s.start + s.label.length,
  };
}
