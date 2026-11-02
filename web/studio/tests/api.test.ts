import { describe, expect, test, vi } from "vitest";
import { ApiError, createApi, readProblem, TOKEN_HEADER, type FetchLike } from "../src/api";

function jsonRes(body: unknown, status = 200, type = "application/json"): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": type } });
}

describe("api client", () => {
  test("test_studio_api_sends_token_header_on_every_request", async () => {
    const fetchFn = vi.fn<FetchLike>(() => Promise.resolve(jsonRes([])));
    const api = createApi("tok123", fetchFn);
    await api.projects();
    await api.saveScript("p", []);
    await api.render("p", "c1", 7);
    await api.select("p", "c1", 2);
    await api.master("p");
    await api.approve("p");
    await api.inject("p", "page.html", "", true);
    expect(fetchFn).toHaveBeenCalledTimes(7);
    for (const [, init] of fetchFn.mock.calls) {
      expect((init?.headers as Record<string, string>)[TOKEN_HEADER]).toBe("tok123");
    }
  });

  test("test_studio_api_request_shapes", async () => {
    const fetchFn = vi.fn<FetchLike>(() => Promise.resolve(jsonRes({})));
    const api = createApi("t", fetchFn);
    await api.render("a b", "c1", 7);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/projects/a%20b/chunks/c1/render");
    expect(fetchFn.mock.calls[0]?.[1]?.body).toBe('{"seed":7}');
    await api.render("p", "c1");
    expect(fetchFn.mock.calls[1]?.[1]?.body).toBe("{}");
    await api.inject("p", "x.html", "#main", false);
    expect(JSON.parse(fetchFn.mock.calls[2]?.[1]?.body as string)).toEqual({
      path: "x.html",
      selector: "#main",
      dry_run: false,
    });
    await api.inject("p", "x.html", "", true);
    expect(JSON.parse(fetchFn.mock.calls[3]?.[1]?.body as string)).toEqual({
      path: "x.html",
      dry_run: true,
    });
  });

  test("test_studio_api_problem_json_error", async () => {
    const problem = {
      type: "about:blank",
      title: "Invalid script",
      status: 422,
      detail: "Chunk 3 is too long.",
      hint: "Split it.",
    };
    const api = createApi("t", () =>
      Promise.resolve(jsonRes(problem, 422, "application/problem+json")),
    );
    const err = await api.project("p").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).problem.status).toBe(422);
    expect((err as ApiError).describe()).toBe("Chunk 3 is too long. Split it.");
  });

  test("test_studio_api_non_json_error_and_network_failure", async () => {
    const res = new Response("boom", { status: 500 });
    expect((await readProblem(res)).title).toBe("Request failed (500)");
    const down = createApi("t", () => Promise.reject(new TypeError("fail")));
    const err = (await down.projects().catch((e: unknown) => e)) as ApiError;
    expect(err.problem.status).toBe(0);
    expect(err.message).toContain("Could not reach");
  });

  test("test_studio_api_media_fetched_with_token_and_cached", async () => {
    URL.createObjectURL = vi.fn(() => "blob:x");
    const fetchFn = vi.fn<FetchLike>(() => Promise.resolve(new Response(new Blob(["a"]))));
    const api = createApi("tok", fetchFn);
    expect(await api.mediaUrl("/media/p/a.wav")).toBe("blob:x");
    await api.mediaUrl("/media/p/a.wav");
    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect((fetchFn.mock.calls[0]?.[1]?.headers as Record<string, string>)[TOKEN_HEADER]).toBe(
      "tok",
    );
  });
});
