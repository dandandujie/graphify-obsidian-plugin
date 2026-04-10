import { spawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import type { AdapterStatus, AssistantAdapter, Provider } from "./types";

export type SpawnFn = typeof spawn;

class CliAssistantAdapter implements AssistantAdapter {
  private currentProcess: ChildProcessWithoutNullStreams | null = null;
  private state: AdapterStatus = "idle";

  constructor(
    public readonly provider: Provider,
    private readonly binary: string,
    private readonly spawnImpl: SpawnFn = spawn
  ) {}

  async startSession(
    prompt: string,
    onChunk: (chunk: string) => void,
    cwd?: string
  ): Promise<void> {
    await this.runPrompt(prompt, onChunk, cwd);
  }

  async send(
    prompt: string,
    onChunk: (chunk: string) => void,
    cwd?: string
  ): Promise<void> {
    await this.runPrompt(prompt, onChunk, cwd);
  }

  cancel(): void {
    if (!this.currentProcess) {
      return;
    }
    this.currentProcess.kill();
    this.currentProcess = null;
    this.state = "cancelled";
  }

  status(): AdapterStatus {
    return this.state;
  }

  private runPrompt(prompt: string, onChunk: (chunk: string) => void, cwd?: string): Promise<void> {
    if (this.currentProcess) {
      this.currentProcess.kill();
      this.currentProcess = null;
    }
    this.state = "running";
    return new Promise((resolve, reject) => {
      const proc = this.spawnImpl(this.binary, [prompt], {
        cwd,
        stdio: ["pipe", "pipe", "pipe"],
      });
      this.currentProcess = proc;

      proc.stdout.on("data", (chunk: Buffer) => onChunk(chunk.toString("utf8")));
      proc.stderr.on("data", (chunk: Buffer) => onChunk(chunk.toString("utf8")));

      proc.on("error", (error) => {
        this.currentProcess = null;
        this.state = "error";
        reject(error);
      });

      proc.on("close", (code) => {
        this.currentProcess = null;
        if (code === 0) {
          this.state = "idle";
          resolve();
          return;
        }
        this.state = "error";
        reject(new Error(`${this.provider} exited with code ${code}`));
      });
    });
  }
}

export class ClaudeCodeAdapter extends CliAssistantAdapter {
  constructor(spawnImpl: SpawnFn = spawn) {
    super("claude", "claude", spawnImpl);
  }
}

export class CodexAdapter extends CliAssistantAdapter {
  constructor(spawnImpl: SpawnFn = spawn) {
    super("codex", "codex", spawnImpl);
  }
}
