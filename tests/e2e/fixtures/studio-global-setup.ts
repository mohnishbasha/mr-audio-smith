import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { copyFileSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../..", import.meta.url));
const WORK = join(ROOT, "tests", "e2e", ".studio-tmp");
const PORT = "7399";
const START_TIMEOUT_MS = 60_000;

/** Narrate the fixture page with the mock backend, then start Studio and publish its session URL. */
export default async function globalSetup(): Promise<() => void> {
  rmSync(WORK, { recursive: true, force: true });
  const out = join(WORK, "out");
  mkdirSync(out, { recursive: true });
  const env = {
    ...process.env,
    AUDIO_SMITH_DEFAULT_BACKEND: "mock",
    PYTHONUNBUFFERED: "1",
  };

  execFileSync(
    "uv",
    [
      "run",
      "mr-audio-smith",
      "run",
      "tests/fixtures/pages/letter-calm.html",
      "--llm",
      "fake",
      "--backend",
      "mock",
      "--out",
      out,
    ],
    { cwd: ROOT, env, stdio: "inherit" },
  );
  copyFileSync(
    join(ROOT, "tests/fixtures/pages/letter-calm.html"),
    join(WORK, "page.html"),
  );

  const server: ChildProcess = spawn(
    "uv",
    [
      "run",
      "mr-audio-smith",
      "studio",
      "--port",
      PORT,
      "--no-open",
      "--out",
      out,
    ],
    { cwd: ROOT, env, stdio: ["ignore", "pipe", "inherit"] },
  );
  const url = await new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error("Studio did not print its URL in time"));
    }, START_TIMEOUT_MS);
    let buf = "";
    server.stdout?.on("data", (chunk: Buffer) => {
      buf += chunk.toString();
      const m = /(http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/.exec(buf);
      if (m?.[1]) {
        clearTimeout(timer);
        resolve(m[1]);
      }
    });
    server.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Studio exited early with code ${String(code)}`));
    });
  });
  process.env["STUDIO_URL"] = url;
  process.env["STUDIO_OUT"] = out;
  process.env["STUDIO_PAGE"] = join(WORK, "page.html");
  process.env["STUDIO_PAGE_REL"] = relative(ROOT, join(WORK, "page.html"));

  return () => {
    server.removeAllListeners("exit");
    server.kill("SIGTERM");
    rmSync(dirname(join(WORK, "x")), { recursive: true, force: true });
  };
}
