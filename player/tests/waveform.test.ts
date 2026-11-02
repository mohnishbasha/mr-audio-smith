import { describe, expect, test } from "vitest";
import { BAR_COUNT, barHeight, createWaveform, parsePeaks } from "../src/waveform";

const PEAKS = Array.from({ length: 28 }, (_, i) => i * 3).join(",");

describe("waveform", () => {
  test("test_player_waveform_parse_peaks_valid", () => {
    expect(parsePeaks(PEAKS)).toHaveLength(BAR_COUNT);
  });

  test("test_player_waveform_parse_peaks_malformed_returns_null", () => {
    expect(parsePeaks(null)).toBeNull();
    expect(parsePeaks("1,2,3")).toBeNull();
    expect(parsePeaks(PEAKS.replace("3", "x"))).toBeNull();
    expect(parsePeaks(Array(28).fill("101").join(","))).toBeNull();
  });

  test("test_player_waveform_bar_height_range", () => {
    expect(barHeight(0)).toBe(8);
    expect(barHeight(100)).toBe(32);
  });

  test("test_player_waveform_bars_left_of_playhead_filled", () => {
    const w = createWaveform();
    w.setPeaks(parsePeaks(PEAKS));
    w.update(0.5, true);
    const bars = [...w.el.querySelectorAll(".bar")];
    expect(bars).toHaveLength(28);
    expect(bars.filter((b) => b.classList.contains("on"))).toHaveLength(14);
    expect(bars[14]?.classList.contains("head")).toBe(true);
    expect(w.el.hasAttribute("data-playing")).toBe(true);
  });

  test("test_player_waveform_ended_fills_all_no_head", () => {
    const w = createWaveform();
    w.setPeaks(parsePeaks(PEAKS));
    w.update(1, false);
    expect(w.el.querySelectorAll(".bar.on")).toHaveLength(28);
    expect(w.el.querySelector(".head")).toBeNull();
  });

  test("test_player_waveform_flat_fallback_without_peaks", () => {
    const w = createWaveform();
    w.update(0.25, false);
    expect(w.el.querySelector(".bar")).toBeNull();
    expect((w.el.querySelector(".fill") as HTMLElement).style.width).toBe("25%");
    w.update(Number.NaN, false);
    expect((w.el.querySelector(".fill") as HTMLElement).style.width).toBe("0%");
  });
});
