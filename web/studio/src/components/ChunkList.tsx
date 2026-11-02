import { useRef } from "preact/hooks";
import {
  pillStatus,
  textOf,
  visibleChunks,
  moveSelection,
  type Filter,
  type ViewState,
} from "../state";
import { Pill } from "./Pill";

interface Props {
  view: ViewState;
  onSelect: (id: string) => void;
  onFilter: (f: Filter) => void;
}

export function ChunkList({ view, onSelect, onFilter }: Props) {
  const list = visibleChunks(view);
  const ref = useRef<HTMLUListElement>(null);
  const all = view.project?.chunks ?? [];

  function onKeyDown(e: KeyboardEvent): void {
    const delta = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (delta === 0) return;
    e.preventDefault();
    const id = moveSelection(view, delta);
    if (id === null) return;
    onSelect(id);
    ref.current?.querySelector<HTMLElement>(`[data-chunk="${CSS.escape(id)}"]`)?.focus();
  }

  return (
    <section aria-labelledby="chunks-h" class="panel">
      <h2 id="chunks-h">Chunks</h2>
      <label class="field">
        <span>Filter</span>
        <select
          value={view.filter}
          onChange={(e) => {
            onFilter(e.currentTarget.value as Filter);
          }}
        >
          <option value="all">All</option>
          <option value="stale">Stale</option>
          <option value="failed">Failed</option>
        </select>
      </label>
      {all.length === 0 && <p>No chunks in this script.</p>}
      {all.length > 0 && list.length === 0 && <p>No chunks match this filter.</p>}
      <ul class="chunk-list" ref={ref} onKeyDown={onKeyDown} aria-label="Chunk list">
        {list.map((c) => {
          const index = all.indexOf(c) + 1;
          const text = textOf(view, c);
          const selected = c.id === view.selectedId;
          return (
            <li key={c.id}>
              <button
                type="button"
                class={`chunk-row${selected ? " selected" : ""}`}
                data-chunk={c.id}
                aria-current={selected ? "true" : undefined}
                onClick={() => {
                  onSelect(c.id);
                }}
              >
                <span class="chunk-num">{String(index).padStart(2, "0")}</span>
                <span class="chunk-snippet">
                  {text.length > 40 ? `${text.slice(0, 40)}...` : text}
                </span>
                <Pill status={pillStatus(view, c)} />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
