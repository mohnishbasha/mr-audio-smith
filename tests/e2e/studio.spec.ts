import { expect, test, type Page } from "@playwright/test";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const external: string[] = [];

function env(name: string): string {
  const v = process.env[name];
  if (!v)
    throw new Error(`${name} is not set; run with playwright.studio.config.ts`);
  return v;
}

test.beforeEach(async ({ page }) => {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.protocol === "http:" || url.protocol === "https:") {
      if (url.hostname !== "127.0.0.1") {
        external.push(url.href);
        await route.abort();
        return;
      }
    }
    await route.continue();
  });
});

test.afterEach(() => {
  expect(external, "requests to hosts other than 127.0.0.1").toEqual([]);
});

async function openProject(page: Page): Promise<void> {
  await page.goto(env("STUDIO_URL"));
  await expect(page).not.toHaveURL(/token=/);
  await page
    .getByRole("button", { name: /letter-calm/ })
    .first()
    .click();
  await expect(page.getByRole("heading", { name: "Chunks" })).toBeVisible();
  await page.locator(".chunk-row").first().click();
}

test.describe.configure({ mode: "serial" });

test("e2e_US017_studio_edit_validate_save_chunk", async ({ page }) => {
  await openProject(page);
  const editor = page.getByLabel("Script text");
  await editor.fill("Hello there [laugh]");
  await expect(
    page.getByRole("list", { name: "Validation errors" }),
  ).toContainText("Unknown marker [laugh]");
  await expect(
    page.getByRole("button", { name: "Save script" }),
  ).toBeDisabled();

  await editor.fill("Hello there friend ");
  await editor.press("End");
  await editor.pressSequentially("[p");
  await expect(
    page.getByRole("button", { name: "Insert [pause 400]" }),
  ).toBeVisible();
  await editor.press("Tab");
  await expect(editor).toHaveValue("Hello there friend [pause 400]");
  await expect(page.locator(".chunk-row").first()).toContainText("Draft");

  await page.getByRole("button", { name: "Save script" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Script saved" }),
  ).toBeVisible();
  await expect(page.locator(".chunk-row").first()).toContainText("Stale");
});

test("e2e_US017_studio_compare_takes_keep_best", async ({ page }) => {
  await openProject(page);
  await page.getByRole("button", { name: "Render take" }).click();
  await expect(page.getByRole("region", { name: "Take A" })).toBeVisible();
  await page.getByRole("button", { name: "Re-render with new seed" }).click();
  const takeB = page.getByRole("region", { name: "Take B" });
  await expect(takeB).toBeVisible();
  await expect(takeB.locator("audio")).toHaveCount(1);
  await expect(takeB).toContainText("Duration");
  await takeB.getByRole("button", { name: "Keep this take" }).click();
  await expect(takeB.getByRole("button", { name: "Kept" })).toBeDisabled();
  await expect(page.locator(".chunk-row").first()).toContainText("Rendered");
});

test("e2e_US017_studio_approve_persists_in_manifest", async ({ page }) => {
  await openProject(page);
  await page.getByRole("button", { name: "Build master" }).click();
  await expect(
    page
      .locator("audio-smith-player, audio[aria-label='Master audio']")
      .first(),
  ).toBeAttached();
  await page
    .getByLabel("I have listened to this narration and approve it.")
    .check();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("This narration is approved.")).toBeVisible();
  const dir = join(env("STUDIO_OUT"), "letter-calm");
  const manifest = readdirSync(dir).find((f) => f.endsWith(".manifest.json"));
  expect(manifest).toBeDefined();
  const text = readFileSync(join(dir, manifest ?? ""), "utf8");
  expect(JSON.parse(text)).toMatchObject({ approved: true });
});

test("e2e_US017_studio_inject_diff_preview_before_write", async ({ page }) => {
  await openProject(page);
  const before = readFileSync(env("STUDIO_PAGE"), "utf8");
  await page.getByLabel("Page path").fill(env("STUDIO_PAGE_REL"));
  await page.getByRole("button", { name: "Preview diff" }).click();
  await expect(page.getByLabel("Dry-run diff")).toBeVisible();
  expect(readFileSync(env("STUDIO_PAGE"), "utf8")).toBe(before);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Injected" }),
  ).toBeVisible();
  expect(readFileSync(env("STUDIO_PAGE"), "utf8")).not.toBe(before);
});

test("e2e_US017_studio_zero_external_requests", async ({ page }) => {
  const seen: string[] = [];
  page.on("request", (r) => seen.push(r.url()));
  await openProject(page);
  await page.getByRole("button", { name: "Build master" }).click();
  await expect(
    page.getByRole("button", { name: "Rebuild master" }),
  ).toBeVisible({ timeout: 60_000 });
  const hosts = new Set(
    seen.filter((u) => u.startsWith("http")).map((u) => new URL(u).hostname),
  );
  expect([...hosts]).toEqual(["127.0.0.1"]);
});
