import {
  App,
  ItemView,
  Modal,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  WorkspaceLeaf,
} from "obsidian";
import { ClaudeCodeAdapter, CodexAdapter } from "./src/adapters";
import { GraphifyCliClient } from "./src/graphify-cli";
import type { AssistantAdapter, Provider } from "./src/types";

const VIEW_TYPE_GRAPHIFY = "graphify-sidebar-view";

interface GraphifyPluginSettings {
  graphifyCliPath: string;
  defaultProvider: Provider;
  reportNotePath: string;
}

const DEFAULT_SETTINGS: GraphifyPluginSettings = {
  graphifyCliPath: "graphify",
  defaultProvider: "claude",
  reportNotePath: "Graphify/GRAPH_REPORT.md",
};

class InputModal extends Modal {
  private value = "";

  constructor(
    app: App,
    private readonly titleText: string,
    private readonly placeholder: string,
    private readonly onSubmit: (value: string) => void
  ) {
    super(app);
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.createEl("h3", { text: this.titleText });
    const input = contentEl.createEl("textarea");
    input.placeholder = this.placeholder;
    input.rows = 4;
    input.addEventListener("input", () => {
      this.value = input.value;
    });
    input.focus();

    const actions = contentEl.createDiv({ cls: "graphify-row" });
    const confirm = actions.createEl("button", { text: "Run" });
    const cancel = actions.createEl("button", { text: "Cancel" });
    confirm.addEventListener("click", () => {
      if (!this.value.trim()) {
        new Notice("Input cannot be empty.");
        return;
      }
      this.close();
      this.onSubmit(this.value.trim());
    });
    cancel.addEventListener("click", () => this.close());
  }
}

class GraphifySidebarView extends ItemView {
  private logEl!: HTMLDivElement;
  private statusEl!: HTMLDivElement;
  private providerSelect!: HTMLSelectElement;
  private promptEl!: HTMLTextAreaElement;

  constructor(leaf: WorkspaceLeaf, private readonly plugin: GraphifyPlugin) {
    super(leaf);
  }

  getViewType(): string {
    return VIEW_TYPE_GRAPHIFY;
  }

  getDisplayText(): string {
    return "Graphify";
  }

  async onOpen(): Promise<void> {
    this.render();
  }

  render(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("graphify-panel");

    contentEl.createEl("h3", { text: "Graphify Control Panel" });

    const providerRow = contentEl.createDiv({ cls: "graphify-row" });
    providerRow.createEl("label", { text: "Provider" });
    this.providerSelect = providerRow.createEl("select");
    this.providerSelect.createEl("option", { text: "Claude Code", value: "claude" });
    this.providerSelect.createEl("option", { text: "Codex", value: "codex" });
    this.providerSelect.value = this.plugin.settings.defaultProvider;
    this.providerSelect.addEventListener("change", async () => {
      const value = this.providerSelect.value as Provider;
      this.plugin.settings.defaultProvider = value;
      await this.plugin.saveSettings();
    });

    this.statusEl = contentEl.createDiv({ cls: "graphify-row" });
    this.statusEl.setText("Status: idle");

    this.promptEl = contentEl.createEl("textarea");
    this.promptEl.placeholder = "Send a prompt to Claude Code / Codex...";
    this.promptEl.rows = 4;

    const promptActions = contentEl.createDiv({ cls: "graphify-row" });
    const sendBtn = promptActions.createEl("button", { text: "Send" });
    const cancelBtn = promptActions.createEl("button", { text: "Cancel" });
    sendBtn.addEventListener("click", async () => {
      const prompt = this.promptEl.value.trim();
      if (!prompt) {
        new Notice("Prompt cannot be empty.");
        return;
      }
      this.promptEl.value = "";
      await this.plugin.sendAssistantPrompt(prompt, this.providerSelect.value as Provider);
    });
    cancelBtn.addEventListener("click", () => this.plugin.cancelAssistantPrompt());

    const actions = contentEl.createDiv({ cls: "graphify-actions" });
    const mkAction = (label: string, fn: () => Promise<void>) => {
      const btn = actions.createEl("button", { text: label });
      btn.addEventListener("click", () => {
        void fn();
      });
    };
    mkAction("Index Vault", () => this.plugin.indexVault());
    mkAction("Incremental Update", () => this.plugin.updateVault());
    mkAction("Query Graph", () => this.plugin.queryVaultFromPrompt());
    mkAction("Generate Report", () => this.plugin.generateReport());
    mkAction("Ingest URL", () => this.plugin.ingestUrlFromPrompt());
    mkAction("Watch Start", () => this.plugin.startWatch());
    mkAction("Watch Stop", () => this.plugin.stopWatch());

    this.logEl = contentEl.createDiv({ cls: "graphify-log" });
    this.log("Graphify panel initialized.");
  }

  setStatus(status: string): void {
    if (this.statusEl) {
      this.statusEl.setText(`Status: ${status}`);
    }
  }

  log(message: string): void {
    if (!this.logEl) {
      return;
    }
    const ts = new Date().toLocaleTimeString();
    const line = `[${ts}] ${message}`;
    this.logEl.setText(`${this.logEl.textContent ?? ""}\n${line}`.trim());
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }
}

class GraphifySettingTab extends PluginSettingTab {
  constructor(app: App, private readonly plugin: GraphifyPlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("Graphify CLI path")
      .setDesc("Binary name or full path to graphify executable.")
      .addText((text) =>
        text
          .setPlaceholder("graphify")
          .setValue(this.plugin.settings.graphifyCliPath)
          .onChange(async (value) => {
            this.plugin.settings.graphifyCliPath = value.trim() || "graphify";
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Default report note")
      .setDesc("Vault path where report note is expected.")
      .addText((text) =>
        text
          .setPlaceholder("Graphify/GRAPH_REPORT.md")
          .setValue(this.plugin.settings.reportNotePath)
          .onChange(async (value) => {
            this.plugin.settings.reportNotePath = value.trim() || "Graphify/GRAPH_REPORT.md";
            await this.plugin.saveSettings();
          })
      );
  }
}

export default class GraphifyPlugin extends Plugin {
  settings: GraphifyPluginSettings = DEFAULT_SETTINGS;
  private adapters: Record<Provider, AssistantAdapter> = {
    claude: new ClaudeCodeAdapter(),
    codex: new CodexAdapter(),
  };

  async onload(): Promise<void> {
    await this.loadSettings();

    this.registerView(VIEW_TYPE_GRAPHIFY, (leaf) => new GraphifySidebarView(leaf, this));
    this.addRibbonIcon("network", "Open Graphify Panel", () => {
      void this.activateView();
    });
    this.addSettingTab(new GraphifySettingTab(this.app, this));

    this.addCommand({
      id: "graphify-index-vault",
      name: "Graphify: Index Vault",
      callback: () => void this.indexVault(),
    });
    this.addCommand({
      id: "graphify-update-vault",
      name: "Graphify: Incremental Update",
      callback: () => void this.updateVault(),
    });
    this.addCommand({
      id: "graphify-query-graph",
      name: "Graphify: Query Graph",
      callback: () => void this.queryVaultFromPrompt(),
    });
    this.addCommand({
      id: "graphify-generate-report",
      name: "Graphify: Generate Report",
      callback: () => void this.generateReport(),
    });
    this.addCommand({
      id: "graphify-ingest-url",
      name: "Graphify: Ingest URL",
      callback: () => void this.ingestUrlFromPrompt(),
    });
    this.addCommand({
      id: "graphify-watch-start",
      name: "Graphify: Start Watch",
      callback: () => void this.startWatch(),
    });
    this.addCommand({
      id: "graphify-watch-stop",
      name: "Graphify: Stop Watch",
      callback: () => void this.stopWatch(),
    });

    await this.activateView();
  }

  async onunload(): Promise<void> {
    await this.app.workspace.detachLeavesOfType(VIEW_TYPE_GRAPHIFY);
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  private getCliClient(): GraphifyCliClient {
    return new GraphifyCliClient({ binary: this.settings.graphifyCliPath });
  }

  private getVaultPath(): string {
    const adapter = this.app.vault.adapter as { basePath?: string };
    if (!adapter.basePath) {
      throw new Error("Desktop vault path is not available in current environment.");
    }
    return adapter.basePath;
  }

  private async withViewLog<T>(task: () => Promise<T>): Promise<T> {
    const view = this.getView();
    if (view) {
      view.setStatus("running");
    }
    try {
      const result = await task();
      if (view) {
        view.setStatus("idle");
      }
      return result;
    } catch (error) {
      if (view) {
        view.setStatus("error");
        view.log(`Error: ${(error as Error).message}`);
      }
      throw error;
    }
  }

  private getView(): GraphifySidebarView | null {
    const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_GRAPHIFY);
    if (leaves.length === 0) {
      return null;
    }
    return leaves[0].view as GraphifySidebarView;
  }

  private log(message: string): void {
    const view = this.getView();
    if (view) {
      view.log(message);
    }
  }

  async activateView(): Promise<void> {
    const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_GRAPHIFY);
    if (leaves.length > 0) {
      await this.app.workspace.revealLeaf(leaves[0]);
      return;
    }
    const leaf = this.app.workspace.getRightLeaf(false);
    if (!leaf) {
      throw new Error("Cannot create Graphify view leaf.");
    }
    await leaf.setViewState({ type: VIEW_TYPE_GRAPHIFY, active: true });
    await this.app.workspace.revealLeaf(leaf);
  }

  async indexVault(): Promise<void> {
    await this.withViewLog(async () => {
      const resp = await this.getCliClient().index(this.getVaultPath());
      this.handleGraphifyResponse(resp);
    });
  }

  async updateVault(): Promise<void> {
    await this.withViewLog(async () => {
      const resp = await this.getCliClient().update(this.getVaultPath());
      this.handleGraphifyResponse(resp);
    });
  }

  async generateReport(): Promise<void> {
    await this.withViewLog(async () => {
      const resp = await this.getCliClient().report(this.getVaultPath());
      this.handleGraphifyResponse(resp);
      if (resp.ok) {
        await this.app.workspace.openLinkText(this.settings.reportNotePath, "", false);
      }
    });
  }

  async queryVaultFromPrompt(): Promise<void> {
    new InputModal(
      this.app,
      "Graphify Query",
      "Ask a graph question...",
      async (question) => {
        await this.withViewLog(async () => {
          const resp = await this.getCliClient().query(this.getVaultPath(), question);
          this.handleGraphifyResponse(resp);
          if (resp.ok && typeof resp.data.answer === "string") {
            this.log(`Query answer:\n${resp.data.answer}`);
          }
        });
      }
    ).open();
  }

  async ingestUrlFromPrompt(): Promise<void> {
    new InputModal(
      this.app,
      "Ingest URL",
      "Paste URL to ingest",
      async (url) => {
        await this.withViewLog(async () => {
          const resp = await this.getCliClient().ingest(this.getVaultPath(), url);
          this.handleGraphifyResponse(resp);
        });
      }
    ).open();
  }

  async startWatch(): Promise<void> {
    await this.withViewLog(async () => {
      const resp = await this.getCliClient().watch(this.getVaultPath(), "start");
      this.handleGraphifyResponse(resp);
    });
  }

  async stopWatch(): Promise<void> {
    await this.withViewLog(async () => {
      const resp = await this.getCliClient().watch(this.getVaultPath(), "stop");
      this.handleGraphifyResponse(resp);
    });
  }

  async sendAssistantPrompt(prompt: string, provider: Provider): Promise<void> {
    const adapter = this.adapters[provider];
    await this.withViewLog(async () => {
      this.log(`Sending prompt to ${provider}...`);
      await adapter.send(
        prompt,
        (chunk) => {
          this.log(`[${provider}] ${chunk.trimEnd()}`);
        },
        this.getVaultPath()
      );
      this.log(`${provider} response completed.`);
    });
  }

  cancelAssistantPrompt(): void {
    const provider = this.settings.defaultProvider;
    this.adapters[provider].cancel();
    this.log(`Cancelled ${provider} session.`);
  }

  private handleGraphifyResponse(resp: {
    ok: boolean;
    code: string;
    message: string;
    data: Record<string, unknown>;
    metrics: Record<string, unknown>;
  }): void {
    const prefix = resp.ok ? "Graphify" : `Graphify (${resp.code})`;
    new Notice(`${prefix}: ${resp.message}`);
    this.log(`${prefix}: ${resp.message}`);
    if (Object.keys(resp.metrics).length > 0) {
      this.log(`Metrics: ${JSON.stringify(resp.metrics)}`);
    }
  }
}
