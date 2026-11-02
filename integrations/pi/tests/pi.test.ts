import { describe, expect, it } from "vitest";
import { AudioSmithClient, AudioSmithError, resolveConfig } from "../src/client.ts";
import { parseNarrateArgs } from "../src/commands.ts";
import { buildContext, createExtension, CONTEXT_MESSAGE_TYPE } from "../src/index.ts";
import { NarrateParams, createTools, formatProgress } from "../src/tools.ts";
import { fakeCtx, fakePi, mockServer, type Handler } from "./helpers.ts";

const noSleep = (): Promise<void> => Promise.resolve();
const polling = { intervalMs: 0, sleep: noSleep };
const view = (
  status: string,
  stage: string | null,
  pct: number,
  chunk?: number,
  total?: number,
) => ({
  body: {
    job_id: "j1",
    status,
    stage,
    progress: { stage_pct: pct, chunk, chunks_total: total },
    created_at: "now",
    error: null,
  },
});
const manifest = {
  body: {
    title: "Page",
    source: "https://x.test",
    voice_id: "v",
    tracks: [{ lang: "en", kind: "main", file: "en.mp3", duration_s: 12.34 }],
    warnings: ["clipped"],
  },
};
const voices: Handler = () => ({
  body: [{ id: "kid", display_name: "Kid", backends: ["mock"], cloned: true }],
});
const profiles: Handler = () => ({ body: [{ id: "story", version: "1", description: "d" }] });

function narrateRoutes() {
  return {
    "POST /v1/jobs": () => ({ status: 202, body: { job_id: "j1" } }),
    "GET /v1/jobs/j1": [
      () => view("queued", null, 0),
      () => view("running", "synth", 0.5, 2, 4),
      () => view("done", "publish", 1),
    ],
    "GET /v1/jobs/j1/manifest": () => manifest,
  };
}

describe("pi extension", () => {
  it("test_pi_schemas_match_mcp_tools", () => {
    const srv = mockServer({});
    const names = createTools(new AudioSmithClient({ baseUrl: "http://h" }, srv.fetch)).map(
      (t) => t.name,
    );
    expect(names).toEqual([
      "mr_audio_smith_narrate",
      "mr_audio_smith_list_voices",
      "mr_audio_smith_list_profiles",
      "mr_audio_smith_list_backends",
      "mr_audio_smith_status",
    ]);
    const props = Object.keys(NarrateParams.properties);
    expect(props).toEqual(["source", "profile", "voice", "backend", "langs"]);
    expect(NarrateParams.required).toEqual(["source"]);
    const narrate = createTools(new AudioSmithClient({ baseUrl: "http://h" }, srv.fetch))[0];
    expect(narrate?.description).toContain("consent record");
  });

  it("test_pi_narrate_command_streams_progress", async () => {
    const srv = mockServer(narrateRoutes());
    const pi = fakePi();
    createExtension({ config: { baseUrl: "http://h", token: "t0k" }, fetch: srv.fetch, polling })(
      pi.api,
    );
    const { ctx, notes } = fakeCtx();
    await pi.commands.get("narrate")?.handler("https://x.test story kid", ctx);
    const text = notes.map((n) => n.msg);
    expect(text).toContain("queued: 0%");
    expect(text).toContain("synth: 50%, chunk 2 of 4");
    expect(text.at(-1)).toContain("en main: en.mp3 (12.3 s)");
    expect(text.at(-1)).toContain("clipped");
    expect(srv.calls[0]?.body).toEqual({
      source: "https://x.test",
      profile: "story",
      voice: "kid",
    });
    expect(srv.calls[0]?.auth).toBe("Bearer t0k");
  });

  it("test_pi_narrate_tool_streams_on_update", async () => {
    const srv = mockServer(narrateRoutes());
    const tool = createTools(new AudioSmithClient({ baseUrl: "http://h" }, srv.fetch), polling)[0];
    const updates: unknown[] = [];
    const result = await tool?.execute(
      "id",
      { source: "https://x.test", langs: ["es"], backend: "mock" },
      undefined,
      (u) => updates.push(u),
      undefined as never,
    );
    expect(updates).toHaveLength(3);
    expect(JSON.stringify(updates[1])).toContain("chunk 2 of 4");
    expect(JSON.stringify(result)).toContain("Narration complete");
    expect(srv.calls[0]?.body).toEqual({
      source: "https://x.test",
      backend: "mock",
      langs: ["es"],
    });
  });

  it("test_pi_context_hook_lists_voices_and_profiles", async () => {
    const srv = mockServer({ "GET /v1/voices": voices, "GET /v1/profiles": profiles });
    const pi = fakePi();
    createExtension({ config: { baseUrl: "http://h" }, fetch: srv.fetch })(pi.api);
    await pi.events.get("session_start")?.({}, {});
    expect(pi.sent).toHaveLength(1);
    expect(pi.sent[0]?.customType).toBe(CONTEXT_MESSAGE_TYPE);
    expect(pi.sent[0]?.display).toBe(false);
    expect(String(pi.sent[0]?.content)).toContain("kid (cloned)");
    expect(String(pi.sent[0]?.content)).toContain("story");
  });

  it("test_pi_context_hook_fails_soft_when_server_down", async () => {
    const srv = mockServer({
      "GET /v1/voices": () => new Error("ECONNREFUSED"),
      "GET /v1/profiles": profiles,
    });
    const pi = fakePi();
    createExtension({ config: { baseUrl: "http://h" }, fetch: srv.fetch })(pi.api);
    await expect(pi.events.get("session_start")?.({}, {})).resolves.toBeUndefined();
    expect(pi.sent).toHaveLength(0);
    expect(
      await buildContext(new AudioSmithClient({ baseUrl: "http://h" }, srv.fetch)),
    ).toBeUndefined();
  });

  it("test_pi_problem_json_maps_to_readable_error", async () => {
    const srv = mockServer({
      "POST /v1/jobs": () => ({
        status: 403,
        problem: true,
        body: { code: "consent_required", detail: "voice kid has no consent", hint: "register it" },
      }),
    });
    const client = new AudioSmithClient({ baseUrl: "http://h" }, srv.fetch);
    const err = await client.submitJob({ source: "x" }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(AudioSmithError);
    expect((err as AudioSmithError).message).toBe(
      "consent_required: voice kid has no consent (hint: register it)",
    );
    expect((err as AudioSmithError).status).toBe(403);
  });

  it("test_pi_narrate_command_reports_failure", async () => {
    const srv = mockServer({
      "POST /v1/jobs": () => ({ status: 202, body: { job_id: "j1" } }),
      "GET /v1/jobs/j1": () => ({
        body: {
          ...view("failed", "synth", 0.1).body,
          error: { code: "backend_failed", detail: "boom", hint: "retry" },
        },
      }),
    });
    const pi = fakePi();
    createExtension({ config: { baseUrl: "http://h" }, fetch: srv.fetch, polling })(pi.api);
    const { ctx, notes } = fakeCtx();
    await pi.commands.get("narrate")?.handler("https://x.test", ctx);
    expect(notes.at(-1)?.type).toBe("error");
    expect(notes.at(-1)?.msg).toContain("backend_failed: boom (hint: retry)");
  });

  it("test_pi_client_unreachable_and_unauthorized", async () => {
    const down = mockServer({ "GET /v1/voices": () => new Error("refused") });
    const c1 = new AudioSmithClient({ baseUrl: "http://h" }, down.fetch);
    await expect(c1.listVoices()).rejects.toThrow(/cannot reach the mr-audio-smith server/);
    const auth = mockServer({
      "GET /v1/voices": () => ({ status: 401 }),
      "GET /v1/profiles": () => ({ status: 500, body: "x" }),
    });
    const c2 = new AudioSmithClient({ baseUrl: "http://h" }, auth.fetch);
    await expect(c2.listVoices()).rejects.toThrow(/AUDIO_SMITH_SERVER_TOKEN/);
    await expect(c2.listProfiles()).rejects.toThrow(/HTTP 500/);
  });

  it("test_pi_wait_for_job_aborts_with_signal", async () => {
    const srv = mockServer({ "GET /v1/jobs/j1": () => view("running", "synth", 0.1) });
    const client = new AudioSmithClient({ baseUrl: "http://h" }, srv.fetch);
    const ac = new AbortController();
    const p = client.waitForJob("j1", { signal: ac.signal, intervalMs: 5 });
    setTimeout(() => {
      ac.abort();
    }, 20);
    await expect(p).rejects.toMatchObject({ code: "aborted" });
    await expect(
      client.waitForJob("j1", { intervalMs: 0, sleep: noSleep, timeoutMs: -1 }),
    ).rejects.toMatchObject({
      code: "timeout",
    });
  });

  it("test_pi_config_from_env_and_overrides", () => {
    expect(
      resolveConfig({ AUDIO_SMITH_SERVER_URL: "http://a:1/", AUDIO_SMITH_SERVER_TOKEN: "t" }),
    ).toEqual({
      baseUrl: "http://a:1",
      token: "t",
    });
    expect(resolveConfig({}).baseUrl).toBe("http://127.0.0.1:8765");
    expect(resolveConfig({ AUDIO_SMITH_SERVER_TOKEN: "t" }, { token: "o" }).token).toBe("o");
    expect(resolveConfig({ AUDIO_SMITH_SERVER_TOKEN: "" }).token).toBeUndefined();
  });

  it("test_pi_voices_and_status_commands", async () => {
    const srv = mockServer({
      "GET /v1/voices": voices,
      "GET /v1/profiles": profiles,
      "GET /healthz": () => ({ body: { status: "ok" } }),
      "GET /readyz": () => ({
        status: 503,
        problem: true,
        body: { code: "not_ready", detail: "no backend" },
      }),
      "GET /v1/jobs/j9": () => view("running", "script", 0.25),
    });
    const pi = fakePi();
    createExtension({ config: { baseUrl: "http://h" }, fetch: srv.fetch })(pi.api);
    expect([...pi.commands.keys()].sort()).toEqual(["audio-status", "narrate", "voices"]);
    const a = fakeCtx();
    await pi.commands.get("voices")?.handler("", a.ctx);
    expect(a.notes[0]?.msg).toContain("voices: kid (cloned)");
    await pi.commands.get("audio-status")?.handler("", a.ctx);
    expect(a.notes[1]?.msg).toContain("ready false");
    await pi.commands.get("audio-status")?.handler("j9", a.ctx);
    expect(a.notes[2]?.msg).toContain("job j1 is running");
    await pi.commands.get("narrate")?.handler("  ", a.ctx);
    expect(a.notes[3]?.type).toBe("warning");
    expect(parseNarrateArgs("u p v")).toEqual({ source: "u", profile: "p", voice: "v" });
  });

  it("test_pi_list_and_status_tools", async () => {
    const srv = mockServer({
      "GET /v1/voices": voices,
      "GET /v1/profiles": profiles,
      "GET /v1/backends": () => ({
        body: [{ id: "mock", available: true, languages: ["en"], cloning: false, license: "MIT" }],
      }),
      "GET /healthz": () => ({ body: {} }),
      "GET /readyz": () => ({ body: { status: "ready" } }),
      "GET /v1/jobs/j1": () => view("running", "synth", 50, 1, 2),
    });
    const tools = createTools(new AudioSmithClient({ baseUrl: "http://h" }, srv.fetch));
    const run = async (name: string, args: unknown): Promise<string> => {
      const t = tools.find((x) => x.name === name);
      return JSON.stringify(await t?.execute("id", args, undefined, undefined, undefined as never));
    };
    expect(await run("mr_audio_smith_list_voices", {})).toContain("kid");
    expect(await run("mr_audio_smith_list_profiles", {})).toContain("story@1");
    expect(await run("mr_audio_smith_list_backends", {})).toContain("mock: available");
    expect(await run("mr_audio_smith_status", {})).toContain("ready: true");
    expect(await run("mr_audio_smith_status", { job_id: "j1" })).toContain(
      "synth: 50%, chunk 1 of 2",
    );
  });

  it("it_harness_pi_extension_loads_and_lists_commands", () => {
    const pi = fakePi();
    createExtension()(pi.api);
    expect(pi.tools.size).toBe(5);
    expect([...pi.commands.keys()].sort()).toEqual(["audio-status", "narrate", "voices"]);
    expect(pi.events.has("session_start")).toBe(true);
    expect(
      formatProgress({
        job_id: "a",
        status: "queued",
        stage: null,
        progress: { stage_pct: 0 },
        created_at: "",
        error: null,
      }),
    ).toBe("queued: 0%");
  });
});
