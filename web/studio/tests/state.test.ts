import { describe, expect, test } from "vitest";
import {
  countChunks,
  initialQueue,
  initialToasts,
  initialView,
  moveSelection,
  nextJob,
  pillStatus,
  queueReducer,
  textOf,
  toastReducer,
  viewReducer,
  visibleChunks,
  type ViewState,
} from "../src/state";
import { takeToken } from "../src/token";
import type { Chunk, Project, Take } from "../src/types";

const chunk = (id: string, status: Chunk["status"] = "cached", text = `text ${id}`): Chunk => ({
  id,
  text,
  verbatim: false,
  status,
  selected_take: null,
  takes: [],
});
const project: Project = {
  slug: "p",
  title: "P",
  source: "s",
  profile: "x",
  lang: "en",
  chunks: [chunk("a"), chunk("b", "stale"), chunk("c", "failed")],
  track: null,
  approved: false,
  warnings: [],
};
const loaded = (): ViewState => viewReducer(initialView, { type: "loaded", project });
const take: Take = { take: 1, seed: 5, similarity: 0.8, duration_ms: 1000, url: "/media/p/t.wav" };

describe("view reducer", () => {
  test("test_studio_reducer_loaded_selects_first", () => {
    expect(loaded().selectedId).toBe("a");
  });

  test("test_studio_reducer_edit_marks_draft_and_reverts", () => {
    let s = viewReducer(loaded(), { type: "edit", id: "a", text: "changed" });
    expect(pillStatus(s, project.chunks[0] as Chunk)).toBe("draft");
    expect(textOf(s, project.chunks[0] as Chunk)).toBe("changed");
    expect(countChunks(s).drafts).toBe(1);
    s = viewReducer(s, { type: "edit", id: "a", text: "text a" });
    expect(countChunks(s).drafts).toBe(0);
  });

  test("test_studio_reducer_filter_and_counts", () => {
    const s = viewReducer(loaded(), { type: "filter", filter: "stale" });
    expect(visibleChunks(s).map((c) => c.id)).toEqual(["b"]);
    expect(countChunks(s)).toMatchObject({ total: 3, stale: 1, failed: 1 });
  });

  test("test_studio_reducer_take_added_and_kept", () => {
    let s = viewReducer(loaded(), { type: "take-added", id: "b", take });
    expect(s.project?.chunks[1]).toMatchObject({ status: "cached", takes: [take] });
    s = viewReducer(s, { type: "take-kept", id: "b", take: 1 });
    expect(s.project?.chunks[1]?.selected_take).toBe(1);
    s = viewReducer(s, { type: "chunk-status", id: "b", status: "rendering" });
    expect(s.project?.chunks[1]?.status).toBe("rendering");
  });

  test("test_studio_reducer_track_and_approved", () => {
    let s = viewReducer(loaded(), {
      type: "track",
      track: { url: "u", captions_url: "c", duration_s: 1, loudness_lufs: -16, peaks: [] },
    });
    s = viewReducer(s, { type: "approved" });
    expect(s.project?.track?.url).toBe("u");
    expect(s.project?.approved).toBe(true);
    expect(viewReducer(initialView, { type: "approved" })).toBe(initialView);
  });

  test("test_studio_reducer_select_and_move", () => {
    let s = viewReducer(loaded(), { type: "select", id: "b" });
    expect(moveSelection(s, 1)).toBe("c");
    expect(moveSelection(s, 5)).toBe("c");
    expect(moveSelection(s, -5)).toBe("a");
    s = viewReducer(s, { type: "loaded", project });
    expect(s.selectedId).toBe("b");
    expect(moveSelection(initialView, 1)).toBeNull();
  });
});

describe("queue reducer", () => {
  test("test_studio_queue_is_sequential_and_dedupes", () => {
    let q = queueReducer(initialQueue, { type: "enqueue", chunkId: "a" });
    q = queueReducer(q, { type: "enqueue", chunkId: "a" });
    q = queueReducer(q, { type: "enqueue", chunkId: "b" });
    expect(q.jobs).toHaveLength(2);
    const first = nextJob(q);
    expect(first?.chunkId).toBe("a");
    q = queueReducer(q, { type: "start", id: first?.id ?? 0 });
    expect(nextJob(q)).toBeNull();
    q = queueReducer(q, { type: "done", id: first?.id ?? 0 });
    expect(nextJob(q)?.chunkId).toBe("b");
  });

  test("test_studio_queue_fail_and_clear", () => {
    let q = queueReducer(initialQueue, { type: "enqueue", chunkId: "a" });
    q = queueReducer(q, { type: "enqueue", chunkId: "b" });
    q = queueReducer(q, { type: "fail", id: 1, error: "bad" });
    expect(q.jobs[0]).toMatchObject({ status: "failed", error: "bad" });
    q = queueReducer(q, { type: "clear" });
    expect(q.jobs.map((j) => j.chunkId)).toEqual(["b"]);
  });
});

describe("toast reducer and token", () => {
  test("test_studio_toasts_add_dismiss", () => {
    let t = toastReducer(initialToasts, { type: "add", kind: "error", message: "x" });
    t = toastReducer(t, { type: "add", kind: "info", message: "y" });
    expect(t.items.map((i) => i.id)).toEqual([1, 2]);
    t = toastReducer(t, { type: "dismiss", id: 1 });
    expect(t.items.map((i) => i.message)).toEqual(["y"]);
  });

  test("test_studio_token_stripped_from_url", () => {
    const calls: string[] = [];
    const history = {
      replaceState: (_s: unknown, _t: string, url: string) => calls.push(url),
    } as unknown as History;
    const loc = { search: "?token=abc&x=1", pathname: "/", hash: "#/p/q" } as Location;
    expect(takeToken(loc, history)).toBe("abc");
    expect(calls).toEqual(["/?x=1#/p/q"]);
    expect(takeToken({ search: "", pathname: "/", hash: "" } as Location, history)).toBeNull();
  });
});
