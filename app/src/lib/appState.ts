import { writable } from "svelte/store";

import type { BackendPaths, CategoryInfo } from "./backend";

const RESOURCE_DIR_KEY = "syntactic-metrics-resource-dir";

export const backendPaths = writable<BackendPaths | null>(null);
export const sourceDir = writable("");
export const resultDir = writable("");
export const categories = writable<CategoryInfo[]>([]);
export const methods = writable<Record<string, boolean>>({
  custom: true,
  leo: true,
  quansyn: true,
  neosca: false,
});
export const resume = writable(true);
export const forceRerun = writable(false);

export const taskRunning = writable(false);
export const currentChildId = writable<number | null>(null);
export const lastTaskStatus = writable<
  "idle" | "running" | "success" | "error" | "cancelled"
>("idle");
export const progress = writable<{
  done: number;
  total: number;
  file: string;
  stage: string;
  category: string;
  stageMessage: string;
} | null>(null);

export const rawLogs = writable<string[]>([]);
export const resourceStatuses = writable<Record<string, string>>({});
export const resourceProgress = writable<
  Record<string, { done: number; total: number }>
>({});
export const resourceErrors = writable<Record<string, string>>({});
export const resourceReady = writable<Record<string, boolean>>({});
/** True while a bulk install-all is in flight (items not started yet show 'queued'). */
export const bulkInstalling = writable(false);
/** In-flight resource child processes: childId -> human label ('Install all', 'Verify', ...). */
export const resourceTasks = writable<Record<number, string>>({});
/** Set when the user asked for install-all while the Python runtime was still bootstrapping. */
export const pendingInstallAll = writable(false);
export const resultFiles = writable<string[]>([]);

export const corpusScan = writable<{
  input: string;
  groups: CategoryInfo[];
  imported?: number;
  skipped?: number;
  progress?: { done: number; total: number };
} | null>(null);

export const corpusImporting = writable(false);
export const corpusScanning = writable(false);
export const corpusMutation = writable(0);

export const alwaysOnTop = writable(false);

export const activeTab = writable("workspace");

export function navigate(tab: string): void {
  activeTab.set(tab);
}

export const resourceDir = writable<string>(
  typeof localStorage !== "undefined"
    ? localStorage.getItem(RESOURCE_DIR_KEY) ?? ""
    : "",
);

export function setResourceDir(dir: string): void {
  resourceDir.set(dir);
  if (typeof localStorage !== "undefined") {
    if (dir) {
      localStorage.setItem(RESOURCE_DIR_KEY, dir);
    } else {
      localStorage.removeItem(RESOURCE_DIR_KEY);
    }
  }
}
