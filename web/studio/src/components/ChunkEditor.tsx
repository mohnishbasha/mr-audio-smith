import { useRef, useState } from "preact/hooks";
import {
  applySuggestion,
  insertMarker,
  markerSuggestion,
  MAX_CHUNK_CHARS,
  validateChunkText,
  type Edit,
  type Suggestion,
} from "../validate";
import type { Chunk } from "../types";
import { MarkerChip } from "./MarkerChip";
import { Pill } from "./Pill";
import type { PillStatus } from "../state";

const MARKERS = ["[pause 400]", "[pause 800]", "[pause 1500]", "*word*"];

interface Props {
  chunk: Chunk;
  index: number;
  text: string;
  status: PillStatus;
  serverErrors: string[];
  onChange: (text: string) => void;
  onRender: () => void;
}

export function ChunkEditor({
  chunk,
  index,
  text,
  status,
  serverErrors,
  onChange,
  onRender,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const errors = validateChunkText(text);

  function restore(edit: Edit): void {
    onChange(edit.text);
    setSuggestion(null);
    setTimeout(() => {
      const ta = ref.current;
      if (!ta) return;
      ta.focus();
      ta.setSelectionRange(edit.caret, edit.caret);
    }, 0);
  }

  function refresh(): void {
    const ta = ref.current;
    if (ta) setSuggestion(markerSuggestion(ta.value, ta.selectionStart));
  }

  function onKeyDown(e: KeyboardEvent): void {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      onRender();
    } else if (e.key === "Tab" && !e.shiftKey && suggestion) {
      e.preventDefault();
      restore(applySuggestion(text, suggestion));
    } else if (e.key === "Escape") {
      setSuggestion(null);
    }
  }

  const over = text.length > MAX_CHUNK_CHARS;
  return (
    <section aria-labelledby="editor-h" class="panel">
      <h2 id="editor-h">
        Chunk {String(index).padStart(2, "0")} <Pill status={status} />
      </h2>
      {status === "stale" && (
        <p class="note">Chunk {index} is stale. Render a take to hear your edit.</p>
      )}
      <div class="chips" role="group" aria-label="Markers">
        {MARKERS.map((m) => (
          <MarkerChip
            key={m}
            marker={m}
            onInsert={(marker) => {
              const el = ref.current;
              restore(
                insertMarker(
                  text,
                  el?.selectionStart ?? text.length,
                  el?.selectionEnd ?? text.length,
                  marker,
                ),
              );
            }}
          />
        ))}
      </div>
      <label class="field">
        <span>Script text</span>
        <textarea
          ref={ref}
          class="mono script-text"
          rows={5}
          value={text}
          aria-invalid={errors.length > 0 || serverErrors.length > 0}
          aria-describedby="editor-count editor-errors"
          onInput={(e) => {
            onChange(e.currentTarget.value);
            setSuggestion(markerSuggestion(e.currentTarget.value, e.currentTarget.selectionStart));
          }}
          onKeyUp={(e) => {
            if (e.key.startsWith("Arrow")) refresh();
          }}
          onClick={refresh}
          onKeyDown={onKeyDown}
        />
      </label>
      {suggestion && (
        <p class="suggest" role="status">
          <button
            type="button"
            class="btn mono"
            onClick={() => {
              restore(applySuggestion(text, suggestion));
            }}
          >
            Accept {suggestion.label}
          </button>
          <span class="muted">or press Tab. Esc dismisses.</span>
        </p>
      )}
      <p id="editor-count" class={over ? "count over" : "count"}>
        {text.length} of {MAX_CHUNK_CHARS} characters
      </p>
      <div id="editor-errors" aria-live="polite">
        {errors.length === 0 && serverErrors.length === 0 ? (
          <p class="ok-text">Validation: 0 errors</p>
        ) : (
          <ul class="errors" aria-label="Validation errors">
            {errors.map((m) => (
              <li key={m}>
                Chunk {index}: {m}
              </li>
            ))}
            {serverErrors.map((m) => (
              <li key={m}>Server: {m}</li>
            ))}
          </ul>
        )}
      </div>
      <div class="row">
        <button
          type="button"
          class="btn btn-primary"
          onClick={onRender}
          disabled={errors.length > 0 || status === "draft" || status === "rendering"}
        >
          Render take
        </button>
        {status === "draft" && <span class="muted">Save the script before rendering.</span>}
      </div>
      {chunk.verbatim && <p class="muted">Verbatim chunk.</p>}
    </section>
  );
}
