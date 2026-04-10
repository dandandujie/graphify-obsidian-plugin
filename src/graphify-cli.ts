import { execFile } from "node:child_process";
import { promisify } from "node:util";
import type { GraphifyResponse } from "./types";

const execFileAsync = promisify(execFile);

export interface GraphifyCliClientOptions {
  binary?: string;
  cwd?: string;
}

function parseJsonPayload(raw: string): GraphifyResponse {
  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    throw new Error("No JSON payload from graphify CLI.");
  }
  const payload = JSON.parse(lines[lines.length - 1]) as GraphifyResponse;
  if (
    typeof payload.ok !== "boolean" ||
    typeof payload.code !== "string" ||
    typeof payload.message !== "string"
  ) {
    throw new Error("Invalid graphify response schema.");
  }
  return payload;
}

export class GraphifyCliClient {
  private readonly binary: string;
  private readonly cwd?: string;

  constructor(options: GraphifyCliClientOptions = {}) {
    this.binary = options.binary ?? "graphify";
    this.cwd = options.cwd;
  }

  async run(args: string[], cwdOverride?: string): Promise<GraphifyResponse> {
    try {
      const { stdout, stderr } = await execFileAsync(this.binary, args, {
        cwd: cwdOverride ?? this.cwd,
        encoding: "utf8",
      });
      return parseJsonPayload(`${stdout}\n${stderr}`);
    } catch (error) {
      const err = error as { stdout?: string; stderr?: string; message: string };
      const merged = `${err.stdout ?? ""}\n${err.stderr ?? ""}`.trim();
      if (merged) {
        try {
          return parseJsonPayload(merged);
        } catch {
          // fall through to generic error response
        }
      }
      return {
        ok: false,
        code: "CLI_EXEC_ERROR",
        message: err.message,
        data: {},
        metrics: {},
      };
    }
  }

  index(vaultPath: string): Promise<GraphifyResponse> {
    return this.run(["obsidian", "index", "--vault", vaultPath]);
  }

  update(vaultPath: string): Promise<GraphifyResponse> {
    return this.run(["obsidian", "update", "--vault", vaultPath]);
  }

  query(vaultPath: string, question: string): Promise<GraphifyResponse> {
    return this.run([
      "obsidian",
      "query",
      "--vault",
      vaultPath,
      "--question",
      question,
    ]);
  }

  report(vaultPath: string): Promise<GraphifyResponse> {
    return this.run(["obsidian", "report", "--vault", vaultPath]);
  }

  ingest(vaultPath: string, url: string): Promise<GraphifyResponse> {
    return this.run([
      "obsidian",
      "ingest",
      "--vault",
      vaultPath,
      "--url",
      url,
    ]);
  }

  watch(vaultPath: string, action: "start" | "stop" | "status"): Promise<GraphifyResponse> {
    return this.run(["obsidian", "watch", "--vault", vaultPath, action]);
  }
}

export const __internal = { parseJsonPayload };
