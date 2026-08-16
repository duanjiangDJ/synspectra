import { bootBridge, currentBridge, onBus } from "../bridge/bridge";
import type {
  BackendPaths,
  CategoryInfo,
  CsvPreview,
  SpawnRequest,
} from "../bridge/contracts";

export type { BackendPaths, CategoryInfo, CsvPreview, SpawnRequest };

async function call<T extends keyof import("../bridge/contracts").RpcMethods>(
  method: T,
  params: import("../bridge/contracts").RpcMethods[T]["params"],
): Promise<import("../bridge/contracts").RpcMethods[T]["result"]> {
  let bridge = currentBridge();
  if (!bridge) {
    bridge = await bootBridge();
  }
  return bridge.request(method, params);
}

export function backendAvailable(): boolean {
  return currentBridge()?.available() ?? false;
}

export async function getBackendPaths(dataDir?: string): Promise<BackendPaths> {
  return call("backend_paths", { dataDir });
}

export async function chooseDirectory(): Promise<string | null> {
  return call("choose_directory", {});
}

export async function chooseZipFile(): Promise<string | null> {
  return call("choose_zip_file", {});
}

export async function scanSourceDir(dir: string): Promise<CategoryInfo[]> {
  return call("scan_source_dir", { sourceDir: dir });
}

export async function scanSourceTree(dir: string): Promise<CategoryInfo[]> {
  return call("scan_source_tree", { sourceDir: dir });
}

export async function listCsvFiles(dir: string): Promise<string[]> {
  return call("list_csv_files", { resultDir: dir });
}

export async function readCsvPreview(path: string, maxRows = 100): Promise<CsvPreview> {
  return call("read_csv_preview", { path, maxRows });
}

export async function pathExists(path: string): Promise<boolean> {
  return call("path_exists", { path });
}

export async function setAlwaysOnTop(enabled: boolean): Promise<void> {
  await call("set_always_on_top", { enabled });
}

export async function setWindowTheme(theme: string): Promise<void> {
  await call("set_theme", { theme });
}

export async function openInFileManager(path: string): Promise<void> {
  await call("open_in_file_manager", { path });
}

export async function bootstrapRuntime(
  uvPath: string,
  requirements: string,
  pythonVersion: string,
  dataDir: string,
): Promise<void> {
  await call("bootstrap_runtime", { uvPath, requirements, pythonVersion, dataDir });
}

export async function spawnBackend(request: SpawnRequest): Promise<number> {
  return call("spawn_backend", { request });
}

export async function killBackend(childId: number): Promise<void> {
  await call("kill_backend", { childId });
}

export function onBackendEvent(callback: (line: string) => void): () => void {
  return onBus("backend://event", callback);
}

export function onBackendRaw(callback: (line: string) => void): () => void {
  return onBus("backend://raw", callback);
}
