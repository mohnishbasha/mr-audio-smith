import { describe, expect, test } from "vitest";
import {
  applySuggestion,
  insertMarker,
  markerSuggestion,
  MAX_CHUNK_CHARS,
  validateChunkText,
} from "../src/validate";

describe("validation", () => {
  test("test_studio_validate_accepts_allowed_markers", () => {
    expect(validateChunkText("Hello [pause 400] world *gently* now.")).toEqual([]);
  });

  test("test_studio_validate_rejects_unknown_marker", () => {
    const errors = validateChunkText("Hello [laugh] world");
    expect(errors).toHaveLength(1);
    expect(errors[0]).toContain("Unknown marker [laugh]");
  });

  test("test_studio_validate_pause_range", () => {
    expect(validateChunkText("a [pause 99] b")).toHaveLength(1);
    expect(validateChunkText("a [pause 3001] b")).toHaveLength(1);
    expect(validateChunkText("a [pause 100] b [pause 3000] c")).toEqual([]);
  });

  test("test_studio_validate_max_chunk_chars", () => {
    expect(validateChunkText("a".repeat(MAX_CHUNK_CHARS))).toEqual([]);
    expect(validateChunkText("a".repeat(MAX_CHUNK_CHARS + 1))[0]).toContain("401 characters");
  });

  test("test_studio_validate_empty_and_stray", () => {
    expect(validateChunkText("   ")).toContain("Chunk text is empty.");
    expect(validateChunkText("oops [pause 400")[0]).toContain("stray bracket");
    expect(validateChunkText("a * b")[0]).toContain("Emphasis");
  });
});

describe("markers", () => {
  test("test_studio_insert_marker_at_caret", () => {
    expect(insertMarker("ab", 1, 1, "[pause 400]")).toEqual({ text: "a[pause 400]b", caret: 12 });
  });

  test("test_studio_insert_emphasis_wraps_selection", () => {
    expect(insertMarker("say hi now", 4, 6, "*word*").text).toBe("say *hi* now");
    expect(insertMarker("x", 1, 1, "*word*").text).toBe("x*word*");
  });

  test("e2e_US017_studio_marker_autocomplete_pause (logic)", () => {
    const s = markerSuggestion("Hello [p", 8);
    expect(s?.label).toBe("[pause 400]");
    expect(s && applySuggestion("Hello [p", s)).toEqual({ text: "Hello [pause 400]", caret: 17 });
    expect(markerSuggestion("Hello [pause 12", 15)?.label).toBe("[pause 12]");
    expect(markerSuggestion("Hello [x", 8)).toBeNull();
    expect(markerSuggestion("Hello", 5)).toBeNull();
    const closing = markerSuggestion("a [p] b", 4);
    expect(closing?.end).toBe(5);
  });
});
