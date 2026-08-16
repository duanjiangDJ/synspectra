import { get } from "svelte/store";

import {
  backendPaths,
  bulkInstalling,
  pendingInstallAll,
  resourceDir,
  corpusImporting,
  corpusMutation,
  corpusScan,
  corpusScanning,
  currentChildId,
  forceRerun,
  lastTaskStatus,
  methods,
  progress,
  rawLogs,
  resourceErrors,
  resourceProgress,
  resourceStatuses,
  resourceTasks,
  resultDir,
  resultFiles,
  sourceDir,
  taskRunning,
} from "./appState";
import {
  getBackendPaths,
  killBackend,
  listCsvFiles,
  onBackendEvent,
  onBackendRaw,
  pathExists,
  spawnBackend,
  type SpawnRequest,
} from "./backend";
import {
  clearBulkState,
  installAllResources,
  refreshResourceReadiness,
} from "./resources";
import { addToast } from "./ui";

let listening = false;

function appendRaw(line: string): void {
  rawLogs.update((items) => [...items.slice(-399), line]);
}

function refreshResults(): void {
  const dir = get(resultDir);
  if (!dir) return;
  listCsvFiles(dir)
    .then((files) => resultFiles.set(files))
    .catch(() => {});
}

function mapResourceStatus(status: string, hasBytes: boolean): string {
  if (status === "downloading") {
    // The uv bootstrap reports downloading without byte counts; "下载中" is
    // the honest status there, "connecting" only when the backend says so.
    return "downloading";
  }
  if (
    status === "verifying" ||
    status === "extracting" ||
    status === "installing"
  ) {
    return "installing";
  }
  return status;
}

export function startListening(): void {
  if (listening) return;
  listening = true;

  onBackendRaw((line) => {
    appendRaw(line);
  });

  onBackendEvent((line) => {
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return;
    }
    if (event.type === "progress") {
      progress.set({
        done: Number(event.done ?? 0),
        total: Number(event.total ?? 0),
        file: String(event.file ?? ""),
        stage: String(event.stage ?? ""),
        category: String(event.category ?? ""),
        stageMessage: get(progress)?.stageMessage ?? "",
      });
    } else if (event.type === "stage") {
      // Keep the run stats (current file / stage / category) live from the
      // backend stage events, not only from per-file progress events.
      const stage = String(event.stage ?? "");
      const message = String(event.message ?? "");
      progress.update((current) => ({
        done: current?.done ?? 0,
        total: current?.total ?? 0,
        file: stage === "file" ? message.split(":")[0].trim() : current?.file ?? "",
        stage,
        category: stage === "category" ? message.replace(/^Starting to process category:\s*/i, "").trim() : current?.category ?? "",
        stageMessage: message,
      }));
    } else if (event.type === "resource") {
      // The shell bootstraps the managed runtime under "python_runtime";
      // the UI exposes the same resource as "python".
      const id =
        event.id === "python_runtime" ? "python" : String(event.id ?? "");
      const status = String(event.status ?? "");
      const detail = String(event.detail ?? "");
      const hasBytes =
        event.bytes_done !== undefined && event.bytes_total !== undefined;
      resourceStatuses.update((items) => ({
        ...items,
        [id]: mapResourceStatus(status, hasBytes),
      }));
      if (status === "download_failed" || status === "install_failed") {
        resourceErrors.update((items) => ({ ...items, [id]: detail }));
        addToast("error", id + ": " + detail.slice(0, 300), 8000);
      } else if (status === "ready") {
        resourceErrors.update((items) => {
          const next = { ...items };
          delete next[id];
          return next;
        });
        addToast("success", id + " ready", 3000);
        void refreshResourceReadiness();
        if (id === "python") {
          // The managed venv now exists: refresh backend paths so buttons,
          // corpus import and runs unblock immediately.
          const paths = get(backendPaths);
          if (paths) {
            const dataDir = get(resourceDir) || paths.data_dir;
            void getBackendPaths(dataDir).then((fresh) => {
              backendPaths.set(fresh);
              // A pending install-all continues automatically once Python is ready.
              if (get(pendingInstallAll)) {
                pendingInstallAll.set(false);
                void installAllResources();
              }
            });
          }
        }
      } else {
        resourceErrors.update((items) => {
          const next = { ...items };
          delete next[id];
          return next;
        });
      }
      resourceProgress.update((items) => ({
        ...items,
        [id]: hasBytes
          ? {
              done: Number(event.bytes_done),
              total: Number(event.bytes_total),
            }
          : { done: 0, total: 0 },
      }));
    } else if (event.type === "corpus") {
      if (event.event === "scan") {
        corpusScan.set({
          input: String(event.input ?? ""),
          groups: (
            event.groups as Array<{ name: string; file_count: number }>
          ).map((group) => ({ name: group.name, file_count: group.file_count })),
        });
        corpusScanning.set(false);
      } else if (event.event === "progress") {
        corpusScan.update((current) => ({
          input: current?.input ?? "",
          groups: current?.groups ?? [],
          progress: {
            done: Number(event.done ?? 0),
            total: Number(event.total ?? 0),
          },
        }));
      } else if (event.event === "done") {
        const imported = Number(event.imported ?? 0);
        const skipped = Number(event.skipped ?? 0);
        corpusImporting.set(false);
        // Clear the confirmation section immediately so the same scan result
        // cannot be imported twice, then trigger a live category refresh.
        corpusScan.set(null);
        corpusMutation.update((value) => value + 1);
        addToast(
          "success",
          "Imported " + imported + " file(s), skipped " + skipped,
        );
      } else if (event.event === "error") {
        corpusImporting.set(false);
        corpusScanning.set(false);
        addToast("error", String(event.detail ?? "Import failed"), 8000);
      } else if (event.event === "renamed" || event.event === "deleted") {
        addToast("info", event.event + ": " + String(event.new ?? event.name ?? ""));
        corpusMutation.update((value) => value + 1);
      }
    } else if (event.type === "child" && event.event === "exit") {
      const childId = Number(event.child_id ?? -1);
      const tasks = get(resourceTasks);
      const label = tasks[childId];
      if (label) {
        resourceTasks.update((items) => {
          const next = { ...items };
          delete next[childId];
          return next;
        });
        const code = event.code === null ? null : Number(event.code);
        addToast(
          code === 0 || code === null ? "success" : "error",
          label + (code === 0 || code === null ? " finished" : " failed"),
          6000,
        );
      } else if (get(bulkInstalling) && Object.keys(tasks).length === 0) {
        // Safety net for a missed registration race: never leave the UI
        // stuck in a bulk-installing state.
        bulkInstalling.set(false);
        resourceStatuses.update((items) => {
          const next = { ...items };
          for (const key of Object.keys(next)) {
            if (next[key] === "queued") delete next[key];
          }
          return next;
        });
        void refreshResourceReadiness();
        return;
      }
      if (Object.keys(get(resourceTasks)).length === 0) {
        bulkInstalling.set(false);
        resourceStatuses.update((items) => {
          const next = { ...items };
          for (const key of Object.keys(next)) {
            if (next[key] === "queued") delete next[key];
          }
          return next;
        });
        void refreshResourceReadiness();
      }
    } else if (event.type === "task" && event.event === "end") {
      taskRunning.set(false);
      currentChildId.set(null);
      if (event.status === "success") {
        lastTaskStatus.set("success");
        addToast("success", "Run completed");
      } else {
        lastTaskStatus.set("error");
        addToast("error", "Run failed");
      }
      refreshResults();
    } else if (event.type === "error") {
      if (event.code === "BOOTSTRAP_FAILED") {
        resourceStatuses.update((items) => ({ ...items, python: "error" }));
        clearBulkState();
      }
      lastTaskStatus.set("error");
      appendRaw(
        "[error] " +
          String(event.title ?? event.detail ?? "") +
          (event.suggestion ? " (" + String(event.suggestion) + ")" : ""),
      );
      addToast(
        "error",
        String(event.title ?? event.detail ?? "").slice(0, 300),
        8000,
      );
    }
  });
}

export async function startRun(): Promise<void> {
  const paths = get(backendPaths);
  const python = paths?.venv_python;
  const script = paths?.run_metrics;
  const source = get(sourceDir);
  const result = get(resultDir);
  if (!paths || !python || !script || !source || !result) {
    appendRaw(
      "[error] Missing prerequisites: configure the workspace and the Python runtime first.",
    );
    return;
  }

  const enabled = Object.entries(get(methods))
    .filter(([, value]) => value)
    .map(([key]) => key);
  if (enabled.length === 0) {
    appendRaw("[error] No method enabled.");
    return;
  }

  const required: Array<[string, string]> = [];
  if (enabled.includes("custom") || enabled.includes("quansyn")) {
    required.push(["Stanza model", paths.data_dir + "/stanza_resources"]);
  }
  if (enabled.includes("leo")) {
    required.push([
      "UDPipe model",
      paths.data_dir + "/models/english-ewt-ud-2.4-190531.udpipe",
    ]);
  }
  if (enabled.includes("neosca")) {
    required.push(
      ["Java runtime", paths.data_dir + "/java"],
      ["Stanford Parser", paths.data_dir + "/stanford/parser"],
      ["Stanford Tregex", paths.data_dir + "/stanford/tregex"],
    );
  }
  for (const [label, resourcePath] of required) {
    if (!(await pathExists(resourcePath))) {
      appendRaw(
        "[error] Missing resource: " +
          label +
          " (" +
          resourcePath +
          "). Install it on the Resources page first.",
      );
      return;
    }
  }

  const args = [
    script,
    "--source-dir",
    source,
    "--result-dir",
    result,
    "--methods",
    enabled.join(","),
    "--log-format",
    "jsonl",
  ];
  if (enabled.includes("leo")) {
    args.push("--leo-model-folder", paths.data_dir + "/models");
  }
  if (get(forceRerun)) args.push("--no-resume");

  const request: SpawnRequest = {
    program: python,
    args,
    env: { ...(paths.env ?? {}), PYTHONUTF8: "1" },
  };
  appendRaw("> " + python + " " + args.join(" "));
  progress.set({ done: 0, total: 0, file: "", stage: "", category: "", stageMessage: "" });
  lastTaskStatus.set("running");
  try {
    const id = await spawnBackend(request);
    taskRunning.set(true);
    currentChildId.set(id);
  } catch (err) {
    lastTaskStatus.set("error");
    appendRaw("[error] " + String(err));
  }
}

export async function stopRun(): Promise<void> {
  const id = get(currentChildId);
  if (id == null) return;
  await killBackend(id);
  taskRunning.set(false);
  currentChildId.set(null);
  lastTaskStatus.set("cancelled");
  addToast("info", "Run cancelled");
}
