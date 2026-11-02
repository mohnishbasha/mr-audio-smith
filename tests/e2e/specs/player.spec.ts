import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PAGE = "/fixtures/player.html";

const audioTime = (page: Page, id = "default"): Promise<number> =>
  page.locator(`#${id} audio`).evaluate((a: HTMLAudioElement) => a.currentTime);
const audioPaused = (page: Page, id = "default"): Promise<boolean> =>
  page.locator(`#${id} audio`).evaluate((a: HTMLAudioElement) => a.paused);
const audioSrc = (page: Page, id = "default"): Promise<string> =>
  page.locator(`#${id} audio`).evaluate((a: HTMLAudioElement) => a.currentSrc);

test("e2e_US006_player_keyboard_play_pause", async ({ page }) => {
  await page.goto(PAGE);
  const play = page.locator("#default .play");
  await play.focus();
  await page.keyboard.press("k");
  await expect.poll(() => audioPaused(page)).toBe(false);
  await expect(play).toHaveAttribute("aria-label", "Pause");
  await page.keyboard.press("k");
  await expect.poll(() => audioPaused(page)).toBe(true);
  await page.locator("#default .wave").focus();
  await page.keyboard.press("Space");
  await expect.poll(() => audioPaused(page)).toBe(false);
  await page.keyboard.press("Space");
  await expect.poll(() => audioPaused(page)).toBe(true);
  await play.focus();
  await page.keyboard.press("Space");
  await expect.poll(() => audioPaused(page)).toBe(false);
});

test("e2e_US006_player_keyboard_arrows_seek_5s", async ({ page }) => {
  await page.goto(PAGE);
  await expect
    .poll(() =>
      page
        .locator("#default audio")
        .evaluate((a: HTMLAudioElement) => a.duration),
    )
    .toBeGreaterThan(4);
  await page.locator("#default .wave").focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => audioTime(page)).toBeCloseTo(5, 0);
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => audioTime(page)).toBe(0);
});

test("e2e_US012_player_captions_toggle", async ({ page }) => {
  await page.goto(PAGE);
  const cc = page.locator("#default .cc");
  const line = page.locator("#default .cap");
  await expect(cc).toBeVisible();
  await expect(cc).toHaveAttribute("aria-pressed", "false");
  await expect(line).toBeHidden();
  await cc.click();
  await expect(cc).toHaveAttribute("aria-pressed", "true");
  await expect(line).toBeVisible();
  await expect(line).toHaveText("Hello little one.");
  await page.locator("#default .wave").focus();
  await page.keyboard.press("c");
  await expect(cc).toHaveAttribute("aria-pressed", "false");
  await expect(line).toBeHidden();
  await page.keyboard.press("c");
  await expect(line).toBeVisible();
  expect(
    await page.locator('#default audio track[kind="captions"]').count(),
  ).toBe(1);
});

test("e2e_US006_player_language_toggle_switches_track", async ({ page }) => {
  await page.goto(PAGE);
  await expect(page.locator("#default .lang button")).toHaveText(["EN", "HI"]);
  expect(await audioSrc(page)).toMatch(/tone\.mp3$/);
  const lang = page.locator("#default").evaluate(
    (el) =>
      new Promise<string>((res) => {
        el.addEventListener(
          "as-language",
          (e) => {
            res((e as CustomEvent<{ lang: string }>).detail.lang);
          },
          { once: true },
        );
      }),
  );
  await page.locator("#default .wave").focus();
  await page.keyboard.press("l");
  expect(await lang).toBe("hi");
  await expect.poll(() => audioSrc(page)).toMatch(/tone-hi\.mp3$/);
  await expect(page.locator("#default .lang button").nth(1)).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await page.locator("#default .lang button").first().click();
  await expect.poll(() => audioSrc(page)).toMatch(/tone\.mp3$/);
  await page.locator("#default .cc").click();
  await page.locator("#default .lang button").nth(1).click();
  await expect(page.locator("#default .cap")).toHaveAttribute("lang", "hi");
  await expect(page.locator("#default .cap")).toHaveText("Namaste chhote.");
});

test.describe("no JavaScript", () => {
  test.use({ javaScriptEnabled: false });
  test("e2e_US006_player_no_js_fallback_plays", async ({ page, request }) => {
    await page.goto(PAGE);
    const audio = page.locator("#default audio");
    await expect(audio).toBeVisible();
    await expect(audio).toHaveAttribute("controls", "");
    const src = await audio.getAttribute("src");
    const res = await request.get(`/fixtures/${src ?? ""}`);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toBe("audio/mpeg");
  });
});

test("e2e_US006_player_no_js_fallback_native_audio_plays", async ({ page }) => {
  await page.goto("/fixtures/player-nojs.html");
  const audio = page.locator("audio");
  await expect(audio).toHaveAttribute("controls", "");
  await audio.evaluate((a: HTMLAudioElement) => a.play());
  await expect
    .poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime))
    .toBeGreaterThan(0.2);
});

test("e2e_US006_player_storage_blocked_still_plays", async ({ page }) => {
  await page.addInitScript(() => {
    const boom = (): never => {
      throw new DOMException("blocked", "SecurityError");
    };
    Object.defineProperty(window, "localStorage", { get: boom });
  });
  await page.goto(PAGE);
  await page.locator("#default .play").click();
  await expect.poll(() => audioTime(page)).toBeGreaterThan(0.2);
  await page.locator("#default .play").click();
  await expect.poll(() => audioPaused(page)).toBe(true);
});

test("e2e_US006_player_remembers_position_per_src", async ({ page }) => {
  await page.goto(PAGE);
  await page.locator("#default .play").click();
  await expect.poll(() => audioTime(page)).toBeGreaterThan(2.2);
  await page.locator("#default .play").click();
  // The position is saved asynchronously; wait until it is stored before reloading (slow CI runners).
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          Object.entries(localStorage).find(([k]) =>
            k.startsWith("as:pos:"),
          )?.[1] ?? "0",
      ),
    )
    .not.toBe("0");
  await page.reload();
  await expect.poll(() => audioTime(page)).toBeGreaterThanOrEqual(2);
});

test("e2e_US006_player_axe_core_zero_violations", async ({ page }) => {
  await page.goto(PAGE);
  await expect(page.locator("#default .play")).toBeVisible();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
  await page.locator("#default .cc").click();
  await page.locator("#default .play").click();
  const active = await new AxeBuilder({ page }).analyze();
  expect(active.violations).toEqual([]);
});

test("e2e_US006_player_axe_core_dark_error_state_zero_violations", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(PAGE);
  await page.locator("#kid audio").evaluate((a: HTMLAudioElement) => {
    a.dispatchEvent(new Event("error"));
  });
  await expect(page.locator("#kid .err")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("e2e_US006_player_kid_size_variant_renders", async ({ page }) => {
  await page.goto(PAGE);
  const kid = await page.locator("#kid .play").boundingBox();
  const normal = await page.locator("#default .play").boundingBox();
  expect(kid?.width).toBe(64);
  expect(kid?.height).toBe(64);
  expect(normal?.width).toBe(44);
  const font = await page
    .locator("#kid .label")
    .evaluate((el) => getComputedStyle(el).fontSize);
  expect(font).toBe("22px");
  for (const sel of [
    "#default .cc",
    "#default .lang button",
    "#default .wave",
  ]) {
    const box = await page.locator(sel).first().boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
  }
});

test("e2e_US006_player_theme_auto_light_dark", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(PAGE);
  const surface = (): Promise<string> =>
    page
      .locator("#default .card")
      .evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(await surface()).toBe("rgb(24, 32, 27)");
  await page.locator("#default").evaluate((el) => {
    el.setAttribute("theme", "light");
  });
  expect(await surface()).toBe("rgb(246, 248, 245)");
  await page.emulateMedia({ colorScheme: "light" });
  await page.locator("#default").evaluate((el) => {
    el.setAttribute("theme", "dark");
  });
  expect(await surface()).toBe("rgb(24, 32, 27)");
});

test("e2e_US006_player_reduced_motion_disables_breathing", async ({ page }) => {
  const headAnimation = (): Promise<string> =>
    page
      .locator("#default .bar.head")
      .evaluate((el) => getComputedStyle(el).animationName);
  await page.goto(PAGE);
  await page.locator("#default .play").click();
  await expect.poll(() => audioTime(page)).toBeGreaterThan(0.2);
  expect(await headAnimation()).toBe("breathe");
  expect(
    await page
      .locator("#default .bar.head")
      .evaluate((el) => getComputedStyle(el).animationDuration),
  ).toBe("1.6s");

  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await headAnimation()).toBe("none");
  await expect(page.locator("#default .bar.on").first()).toBeVisible();
});

test("e2e_US006_player_media_session_metadata_set", async ({ page }) => {
  await page.goto(PAGE);
  await page.locator("#default .play").click();
  await expect
    .poll(() => page.evaluate(() => navigator.mediaSession.metadata?.title))
    .toBe("Listen to Dad read this letter");
  expect(
    await page.evaluate(() => navigator.mediaSession.metadata?.artist),
  ).toBe("Dad");
});
