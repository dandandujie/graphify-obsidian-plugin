import { EventEmitter } from "node:events";
import { describe, expect, it } from "vitest";
import { ClaudeCodeAdapter, CodexAdapter } from "../adapters";

class FakeStream extends EventEmitter {}

class FakeProcess extends EventEmitter {
  stdout = new FakeStream();
  stderr = new FakeStream();
  killed = false;

  kill(): boolean {
    this.killed = true;
    this.emit("close", 0);
    return true;
  }
}

describe("assistant adapters", () => {
  it("streams chunks and returns to idle on success", async () => {
    const fake = new FakeProcess();
    const spawn = () => {
      setTimeout(() => {
        fake.stdout.emit("data", Buffer.from("hello"));
        fake.emit("close", 0);
      }, 0);
      return fake as any;
    };

    const adapter = new ClaudeCodeAdapter(spawn as any);
    let output = "";
    await adapter.send("test", (chunk) => {
      output += chunk;
    });
    expect(output).toContain("hello");
    expect(adapter.status()).toBe("idle");
  });

  it("cancel switches adapter status", async () => {
    const fake = new FakeProcess();
    const spawn = () => fake as any;

    const adapter = new CodexAdapter(spawn as any);
    const promise = adapter.send("test", () => {
      // no-op
    });
    adapter.cancel();
    await promise;
    expect(adapter.status()).toBe("cancelled");
  });
});
