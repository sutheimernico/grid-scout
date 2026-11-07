import { describe, expect, it } from "vitest";
import { readArtifact } from "./useData";

const respond = (status: number, body: string) => (async () => new Response(body, { status })) as unknown as typeof fetch;

describe("readArtifact", () => {
  it("reads valid JSON", async () => {
    expect(await readArtifact("x", respond(200, '{"a":1}'))).toEqual({ state: "ready", data: { a: 1 } });
  });
  it("calls a 404 missing: the pipeline has not produced it yet", async () => {
    expect(await readArtifact("x", respond(404, "nope"))).toEqual({ state: "missing" });
  });
  it("calls an HTML index page served for a .json path missing too", async () => {
    const spa = (async () => new Response("<!doctype html>", { status: 200, headers: { "content-type": "text/html" } })) as unknown as typeof fetch;
    expect(await readArtifact("x", spa)).toEqual({ state: "missing" });
  });
  it("calls a corrupt body an error, not 'not produced yet'", async () => {
    expect(await readArtifact("x", respond(200, '{"a":'))).toEqual({ state: "error" });
  });
  it("calls a server error or a network failure an error", async () => {
    expect(await readArtifact("x", respond(500, "boom"))).toEqual({ state: "error" });
    const down = (async () => {
      throw new TypeError("offline");
    }) as unknown as typeof fetch;
    expect(await readArtifact("x", down)).toEqual({ state: "error" });
  });
});
