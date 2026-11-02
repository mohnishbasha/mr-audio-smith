import type { Chunk, ChunkStatus, Project, Take, Track } from "./types";

export type Filter = "all" | "stale" | "failed";
export type PillStatus = ChunkStatus | "draft";

export interface ViewState {
  project: Project | null;
  drafts: Record<string, string>;
  selectedId: string | null;
  filter: Filter;
}

export type ViewAction =
  | { type: "loaded"; project: Project }
  | { type: "select"; id: string }
  | { type: "edit"; id: string; text: string }
  | { type: "filter"; filter: Filter }
  | { type: "chunk-status"; id: string; status: ChunkStatus }
  | { type: "take-added"; id: string; take: Take }
  | { type: "take-kept"; id: string; take: number }
  | { type: "track"; track: Track }
  | { type: "approved" };

export const initialView: ViewState = {
  project: null,
  drafts: {},
  selectedId: null,
  filter: "all",
};

function mapChunk(state: ViewState, id: string, fn: (c: Chunk) => Chunk): ViewState {
  if (!state.project) return state;
  return {
    ...state,
    project: {
      ...state.project,
      chunks: state.project.chunks.map((c) => (c.id === id ? fn(c) : c)),
    },
  };
}

export function viewReducer(state: ViewState, action: ViewAction): ViewState {
  switch (action.type) {
    case "loaded": {
      const keep = action.project.chunks.some((c) => c.id === state.selectedId);
      return {
        ...state,
        project: action.project,
        drafts: {},
        selectedId: keep ? state.selectedId : (action.project.chunks[0]?.id ?? null),
      };
    }
    case "select":
      return { ...state, selectedId: action.id };
    case "edit": {
      const original = state.project?.chunks.find((c) => c.id === action.id)?.text;
      const rest = Object.fromEntries(
        Object.entries(state.drafts).filter(([id]) => id !== action.id),
      );
      const drafts = action.text === original ? rest : { ...rest, [action.id]: action.text };
      return { ...state, drafts };
    }
    case "filter":
      return { ...state, filter: action.filter };
    case "chunk-status":
      return mapChunk(state, action.id, (c) => ({ ...c, status: action.status }));
    case "take-added":
      return mapChunk(state, action.id, (c) => ({
        ...c,
        status: "cached",
        takes: [...c.takes.filter((t) => t.take !== action.take.take), action.take],
      }));
    case "take-kept":
      return mapChunk(state, action.id, (c) => ({ ...c, selected_take: action.take }));
    case "track":
      return state.project
        ? { ...state, project: { ...state.project, track: action.track } }
        : state;
    case "approved":
      return state.project ? { ...state, project: { ...state.project, approved: true } } : state;
  }
}

export function textOf(state: ViewState, chunk: Chunk): string {
  return state.drafts[chunk.id] ?? chunk.text;
}

export function pillStatus(state: ViewState, chunk: Chunk): PillStatus {
  return chunk.id in state.drafts ? "draft" : chunk.status;
}

export const PILL_LABEL: Record<PillStatus, string> = {
  cached: "Rendered",
  stale: "Stale",
  rendering: "Rendering",
  failed: "Failed",
  draft: "Draft",
};

export function visibleChunks(state: ViewState): Chunk[] {
  const chunks = state.project?.chunks ?? [];
  if (state.filter === "all") return chunks;
  return chunks.filter((c) => c.status === state.filter);
}

export interface Counts {
  total: number;
  stale: number;
  failed: number;
  rendering: number;
  drafts: number;
}

export function countChunks(state: ViewState): Counts {
  const chunks = state.project?.chunks ?? [];
  const n = (s: ChunkStatus): number => chunks.filter((c) => c.status === s).length;
  return {
    total: chunks.length,
    stale: n("stale"),
    failed: n("failed"),
    rendering: n("rendering"),
    drafts: Object.keys(state.drafts).length,
  };
}

/** Move the selection by delta within the visible list, clamped at both ends. */
export function moveSelection(state: ViewState, delta: number): string | null {
  const list = visibleChunks(state);
  if (list.length === 0) return null;
  const at = list.findIndex((c) => c.id === state.selectedId);
  const next = Math.min(list.length - 1, Math.max(0, (at < 0 ? 0 : at) + delta));
  return list[next]?.id ?? null;
}

/* Render queue: strictly sequential. */

export type JobStatus = "queued" | "rendering" | "rendered" | "failed";

export interface Job {
  id: number;
  chunkId: string;
  status: JobStatus;
  error: string;
}

export interface QueueState {
  jobs: Job[];
  nextId: number;
}

export type QueueAction =
  | { type: "enqueue"; chunkId: string }
  | { type: "start"; id: number }
  | { type: "done"; id: number }
  | { type: "fail"; id: number; error: string }
  | { type: "clear" };

export const initialQueue: QueueState = { jobs: [], nextId: 1 };

export function queueReducer(state: QueueState, action: QueueAction): QueueState {
  const set = (id: number, patch: Partial<Job>): QueueState => ({
    ...state,
    jobs: state.jobs.map((j) => (j.id === id ? { ...j, ...patch } : j)),
  });
  switch (action.type) {
    case "enqueue": {
      const dup = state.jobs.some(
        (j) => j.chunkId === action.chunkId && (j.status === "queued" || j.status === "rendering"),
      );
      if (dup) return state;
      const job: Job = { id: state.nextId, chunkId: action.chunkId, status: "queued", error: "" };
      return { jobs: [...state.jobs, job], nextId: state.nextId + 1 };
    }
    case "start":
      return set(action.id, { status: "rendering" });
    case "done":
      return set(action.id, { status: "rendered" });
    case "fail":
      return set(action.id, { status: "failed", error: action.error });
    case "clear":
      return {
        ...state,
        jobs: state.jobs.filter((j) => j.status === "queued" || j.status === "rendering"),
      };
  }
}

/** The next job to run, or null while one is already rendering. */
export function nextJob(state: QueueState): Job | null {
  if (state.jobs.some((j) => j.status === "rendering")) return null;
  return state.jobs.find((j) => j.status === "queued") ?? null;
}

export const JOB_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  rendering: "Rendering",
  rendered: "Rendered",
  failed: "Failed",
};

/* Toasts. */

export type ToastKind = "info" | "success" | "error";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

export interface ToastState {
  items: ToastItem[];
  nextId: number;
}

export type ToastAction =
  { type: "add"; kind: ToastKind; message: string } | { type: "dismiss"; id: number };

export const initialToasts: ToastState = { items: [], nextId: 1 };

export function toastReducer(state: ToastState, action: ToastAction): ToastState {
  if (action.type === "dismiss") {
    return { ...state, items: state.items.filter((t) => t.id !== action.id) };
  }
  const item: ToastItem = { id: state.nextId, kind: action.kind, message: action.message };
  return { items: [...state.items, item], nextId: state.nextId + 1 };
}
