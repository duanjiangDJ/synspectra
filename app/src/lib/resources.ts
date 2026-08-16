import { get } from "svelte/store";

import {
  backendPaths,
  bulkInstalling,
  pendingInstallAll,
  resourceDir,
  resourceReady,
  resourceStatuses,
  resourceTasks,
} from "./appState";
import {
  bootstrapRuntime,
  getBackendPaths,
  pathExists,
  spawnBackend,
  type SpawnRequest,
} from "./backend";
import { addToast } from "./ui";

function buildRequest(script: string, args: string[]): SpawnRequest {
  const paths = get(backendPaths);
  if (!paths?.venv_python || !paths.manifest) {
    throw new Error("Python runtime is not installed yet.");
  }
  const dataDir = get(resourceDir) || paths.data_dir;
  return {
    program: paths.venv_python,
    args: [
      script,
      "--data-dir",
      dataDir,
      "--manifest",
      paths.manifest,
      "--log-format",
      "jsonl",
      ...args,
    ],
    env: { ...(paths.env ?? {}), PYTHONUTF8: "1" },
  };
}

/** Tracks a spawned resource child so the UI can react when it exits. */
export async function trackResourceChild(
  label: string,
  request: SpawnRequest,
): Promise<void> {
  const childId = await spawnBackend(request);
  resourceTasks.update((items) => ({ ...items, [childId]: label }));
}

function markStatus(id: string, status: string): void {
  resourceStatuses.update((items) => ({ ...items, [id]: status }));
}

export async function installResource(resourceId: string): Promise<void> {
  const paths = get(backendPaths);
  if (!paths?.venv_python || !paths.resource_manager || !paths.manifest) return;
  // Synchronous status so the button disables immediately (double-click safe).
  markStatus(resourceId, "connecting");
  await trackResourceChild(
    "Install " + resourceId,
    buildRequest(paths.resource_manager, ["install", resourceId]),
  );
}

/** Resets every bulk-install marker so the UI can never stay locked. */
export function clearBulkState(): void {
  bulkInstalling.set(false);
  pendingInstallAll.set(false);
  resourceStatuses.update((items) => {
    const next = { ...items };
    for (const key of Object.keys(next)) {
      if (next[key] === "queued") delete next[key];
    }
    return next;
  });
}

export async function installAllResources(): Promise<void> {
  const paths = get(backendPaths);
  if (!paths?.resource_manager || !paths.manifest) return;
  const ready = get(resourceReady);

  // Everything not installed yet shows "queued" so the user sees the full
  // plan; items become live once their own events arrive.
  bulkInstalling.set(true);
  for (const id of ["udpipe_model", "stanza_model", "jre", "stanford_parser", "stanford_tregex"]) {
    if (!ready[id]) markStatus(id, "queued");
  }

  // The managed Python runtime is bootstrapped by the shell (uv), not by
  // resource_manager. Bootstrap first; the python ready event automatically
  // continues with the resource_manager install-all.
  if (!ready.python || !paths.venv_python) {
    if (paths.uv && paths.requirements_lock) {
      pendingInstallAll.set(true);
      await bootstrapPythonRuntime();
      return;
    }
    clearBulkState();
    addToast("error", "uv is not available; cannot bootstrap the Python runtime.", 8000);
    return;
  }

  try {
    await trackResourceChild(
      "Install all",
      buildRequest(paths.resource_manager, ["install", "all"]),
    );
  } catch (err) {
    // Do not leave the UI stuck in a bulk-installing state.
    clearBulkState();
    addToast("error", "Install all failed: " + String(err), 8000);
  }
}

export async function verifyResources(): Promise<void> {
  const paths = get(backendPaths);
  if (!paths?.venv_python || !paths.resource_manager || !paths.manifest) return;
  await trackResourceChild(
    "Verify",
    buildRequest(paths.resource_manager, ["verify", "all"]),
  );
}

export async function importOfflineBundle(bundlePath: string): Promise<void> {
  const paths = get(backendPaths);
  if (!paths?.venv_python || !paths.resource_manager || !paths.manifest) return;
  await trackResourceChild(
    "Offline import",
    buildRequest(paths.resource_manager, ["offline-import", bundlePath]),
  );
}

export async function uninstallResource(resourceId: string): Promise<void> {
  const paths = get(backendPaths);
  if (!paths?.venv_python || !paths.resource_manager || !paths.manifest) return;
  markStatus(resourceId, "installing");
  await trackResourceChild(
    "Uninstall " + resourceId,
    buildRequest(paths.resource_manager, ["uninstall", resourceId]),
  );
}

export async function uninstallPythonRuntime(): Promise<void> {
  const paths = get(backendPaths);
  if (!paths?.venv_python || !paths.resource_manager || !paths.manifest) return;
  markStatus("python", "installing");
  await trackResourceChild(
    "Uninstall python_runtime",
    buildRequest(paths.resource_manager, ["uninstall", "python_runtime"]),
  );
}

export async function bootstrapPythonRuntime(): Promise<void> {
  const paths = get(backendPaths);
  if (!paths?.uv || !paths.requirements_lock) {
    markStatus("python", "error");
    addToast("error", "uv is not available; cannot bootstrap the Python runtime.", 8000);
    return;
  }
  markStatus("python", "installing");
  const dataDir = get(resourceDir) || paths.data_dir;
  try {
    const next = await getBackendPaths(dataDir);
    backendPaths.set(next);
    await bootstrapRuntime(
      next.uv!,
      paths.requirements_lock,
      "3.11",
      dataDir,
    );
  } catch (err) {
    markStatus("python", "error");
    addToast("error", "Python runtime bootstrap failed: " + String(err), 8000);
  }
}

/**
 * Detect which resources are installed and publish them to the resourceReady
 * store. The Config page uses the same store to gate methods whose resources
 * are missing, and the Resources page uses it for status display.
 */
export async function refreshResourceReadiness(): Promise<void> {
  const paths = get(backendPaths);
  if (!paths) {
    resourceReady.set({});
    return;
  }
  const targets: Record<string, string | null> = {
    python: paths.venv_python,
    stanza_model: paths.env?.STANZA_RESOURCES_DIR ?? null,
    udpipe_model: paths.data_dir + "/models/english-ewt-ud-2.4-190531.udpipe",
    jre: paths.data_dir + "/java",
    stanford_parser: paths.data_dir + "/stanford/parser",
    stanford_tregex: paths.data_dir + "/stanford/tregex",
  };
  const next: Record<string, boolean> = {};
  for (const [id, target] of Object.entries(targets)) {
    next[id] = target ? await pathExists(target) : false;
  }
  resourceReady.set(next);
}

/** Resource ids required by each metric method. */
export const METHOD_RESOURCE_DEPS: Record<string, string[]> = {
  custom: ["python", "stanza_model"],
  leo: ["python", "udpipe_model"],
  quansyn: ["python", "stanza_model"],
  neosca: ["python", "jre", "stanford_parser", "stanford_tregex"],
};

export function isMethodReady(method: string, ready: Record<string, boolean>): boolean {
  const deps = METHOD_RESOURCE_DEPS[method] ?? [];
  return deps.every((id) => ready[id] === true);
}
