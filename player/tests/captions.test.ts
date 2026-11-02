import { afterEach, describe, expect, test, vi } from "vitest";
import { activeCueIndex, fetchCues, parseVtt } from "../src/captions";

const VTT = `WEBVTT

NOTE a comment

1
00:00:00.000 --> 00:00:02.500
Hello <v Dad>little one.

00:00:02.500 --> 00:01:05.000
Second line
wraps here.
`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("captions", () => {
  test("test_player_captions_parse_webvtt_cues", () => {
    const cues = parseVtt(VTT);
    expect(cues).toHaveLength(2);
    expect(cues[0]).toEqual({ start: 0, end: 2.5, text: "Hello little one." });
    expect(cues[1]?.text).toBe("Second line wraps here.");
    expect(cues[1]?.end).toBe(65);
  });

  test("test_player_captions_cue_active_class_follows_time", () => {
    const cues = parseVtt(VTT);
    expect(activeCueIndex(cues, 0)).toBe(0);
    expect(activeCueIndex(cues, 2.49)).toBe(0);
    expect(activeCueIndex(cues, 2.5)).toBe(1);
    expect(activeCueIndex(cues, 99)).toBe(-1);
  });

  test("test_player_captions_ignore_malformed_blocks", () => {
    expect(parseVtt("WEBVTT\n\nnot a cue\n\nbad --> worse\nx")).toEqual([]);
  });

  test("test_player_captions_fetch_rejects_on_http_error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("", { status: 404 }))),
    );
    await expect(fetchCues("a.vtt")).rejects.toThrow();
  });

  test("test_player_captions_fetch_parses_body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(VTT))),
    );
    expect(await fetchCues("a.vtt")).toHaveLength(2);
  });
});
