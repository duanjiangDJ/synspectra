import { get, writable } from "svelte/store";

import type { BackendPaths, CategoryInfo } from "./backend";

const RESOURCE_DIR_KEY = "syntactic-metrics-resource-dir";
const CATEGORY_LANGUAGES_KEY = "syntactic-metrics-category-languages";
const DEFAULT_LANGUAGE_KEY = "syntactic-metrics-default-language";

function readLanguageOverrides(key: string): Record<string, string> {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

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

export const defaultLanguage = writable<string>(
  typeof localStorage !== "undefined"
    ? localStorage.getItem(DEFAULT_LANGUAGE_KEY) ?? "en"
    : "en",
);

export function setDefaultLanguage(language: string): void {
  defaultLanguage.set(language);
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(DEFAULT_LANGUAGE_KEY, language);
  }
}

/** Per-category language overrides, keyed by "sourceDir::category". */
export const categoryLanguages = writable<Record<string, string>>(
  readLanguageOverrides(CATEGORY_LANGUAGES_KEY),
);

export function categoryLanguageKey(sourceDir: string, category: string): string {
  return sourceDir + "::" + category;
}

export function setCategoryLanguage(
  sourceDir: string,
  category: string,
  language: string,
): void {
  categoryLanguages.update((items) => {
    const next = {
      ...items,
      [categoryLanguageKey(sourceDir, category)]: language,
    };
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(CATEGORY_LANGUAGES_KEY, JSON.stringify(next));
    }
    return next;
  });
}

export function languageForCategory(sourceDir: string, category: string): string {
  const overrides = get(categoryLanguages);
  return (
    overrides[categoryLanguageKey(sourceDir, category)] ?? get(defaultLanguage)
  );
}
