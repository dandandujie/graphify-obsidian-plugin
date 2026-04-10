export type Provider = "claude" | "codex";

export interface GraphifyResponse {
  ok: boolean;
  code: string;
  message: string;
  data: Record<string, unknown>;
  metrics: Record<string, unknown>;
}

export type AdapterStatus = "idle" | "running" | "cancelled" | "error";

export interface AssistantAdapter {
  readonly provider: Provider;
  startSession(
    prompt: string,
    onChunk: (chunk: string) => void,
    cwd?: string
  ): Promise<void>;
  send(
    prompt: string,
    onChunk: (chunk: string) => void,
    cwd?: string
  ): Promise<void>;
  cancel(): void;
  status(): AdapterStatus;
}
