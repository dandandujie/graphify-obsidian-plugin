import { describe, expect, it, vi } from "vitest";
import { GraphifyCliClient, __internal } from "../graphify-cli";

describe("graphify-cli parser", () => {
  it("parses last JSON line", () => {
    const payload = __internal.parseJsonPayload(
      "warning line\n" +
        JSON.stringify({
          ok: true,
          code: "OK",
          message: "done",
          data: {},
          metrics: {},
        })
    );
    expect(payload.ok).toBe(true);
    expect(payload.code).toBe("OK");
  });

  it("throws on invalid schema", () => {
    expect(() => __internal.parseJsonPayload('{"foo":"bar"}')).toThrow();
  });
});

describe("graphify-cli command wrappers", () => {
  it("builds index args", async () => {
    const client = new GraphifyCliClient();
    const spy = vi.spyOn(client, "run").mockResolvedValue({
      ok: true,
      code: "OK",
      message: "done",
      data: {},
      metrics: {},
    });

    await client.index("/vault");
    expect(spy).toHaveBeenCalledWith(["obsidian", "index", "--vault", "/vault"]);
  });

  it("builds watch args", async () => {
    const client = new GraphifyCliClient();
    const spy = vi.spyOn(client, "run").mockResolvedValue({
      ok: true,
      code: "OK",
      message: "done",
      data: {},
      metrics: {},
    });

    await client.watch("/vault", "status");
    expect(spy).toHaveBeenCalledWith([
      "obsidian",
      "watch",
      "--vault",
      "/vault",
      "status",
    ]);
  });
});
