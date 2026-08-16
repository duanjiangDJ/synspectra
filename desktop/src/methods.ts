import { parse } from "csv-parse/sync";
import { dialog, nativeTheme, shell, type BrowserWindow } from "electron";
import * as fs from "fs";
import * as path from "path";

import { startBootstrapRuntime } from "./bootstrap";
import { resolveBackendPaths, type DesktopContext } from "./paths";
import { Supervisor, type SpawnRequest } from "./supervisor";

export interface CategoryInfo {
  name: string;
  file_count: number;
}

export type EmitFn = (payload: Record<string, unknown>) => void;

/** Forwards a raw child line under its own event stream. */
export type EmitLineFn = (stream: string, line: string) => void;

export type RpcHandler = (params: Record<string, unknown>) => unknown;

function listTxtFiles(dir: string): number {
  let count = 0;
  try {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isFile() && entry.name.toLowerCase().endsWith(".txt")) count += 1;
    }
  } catch {
    return 0;
  }
  return count;
}

function scanSourceDir(sourceDir: string): CategoryInfo[] {
  const categories: CategoryInfo[] = [];
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(sourceDir, { withFileTypes: true });
  } catch {
    return categories;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    if (entry.name.endsWith("_results_dd")) continue;
    categories.push({
      name: entry.name,
      file_count: listTxtFiles(path.join(sourceDir, entry.name)),
    });
  }
  categories.sort((a, b) => a.name.localeCompare(b.name));
  return categories;
}

function walkTree(
  dir: string,
  rel: string,
  depth: number,
  out: CategoryInfo[],
): void {
  if (depth > 10) return;
  let txtCount = 0;
  const subdirs: string[] = [];
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (entry.name.endsWith("_results_dd")) continue;
    if (entry.isDirectory()) {
      subdirs.push(entry.name);
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".txt")) {
      txtCount += 1;
    }
  }
  if (txtCount > 0) {
    out.push({
      name: rel === "" ? path.basename(dir) : rel,
      file_count: txtCount,
    });
  }
  for (const child of subdirs) {
    const nextRel = rel === "" ? child : rel + "/" + child;
    walkTree(path.join(dir, child), nextRel, depth + 1, out);
  }
}

function scanSourceTree(sourceDir: string): CategoryInfo[] {
  const groups: CategoryInfo[] = [];
  walkTree(sourceDir, "", 0, groups);
  groups.sort((a, b) => a.name.localeCompare(b.name));
  return groups;
}

export function createMethodHandlers(options: {
  ctx: DesktopContext;
  supervisor: Supervisor;
  getWindow: () => BrowserWindow | null;
  emit: EmitFn;
  emitLine: EmitLineFn;
  logLine: (level: string, message: string) => void;
}): Record<string, RpcHandler> {
  const { ctx, supervisor, getWindow, emit, emitLine, logLine } = options;

  return {
    backend_paths: (params) =>
      resolveBackendPaths(ctx, typeof params?.dataDir === "string" ? params.dataDir : undefined),

    scan_source_dir: (params) => scanSourceDir(String(params?.sourceDir ?? "")),

    scan_source_tree: (params) => scanSourceTree(String(params?.sourceDir ?? "")),

    list_csv_files: (params) => {
      const dir = String(params?.resultDir ?? "");
      let entries: fs.Dirent[];
      try {
        entries = fs.readdirSync(dir, { withFileTypes: true });
      } catch {
        return [];
      }
      return entries
        .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".csv"))
        .map((entry) => entry.name)
        .sort();
    },

    read_csv_preview: (params) => {
      const csvPath = String(params?.path ?? "");
      const maxRows = Math.min(Number(params?.maxRows ?? 100) || 100, 500);
      const content = fs.readFileSync(csvPath, "utf8");
      const records: string[][] = parse(content, {
        skip_empty_lines: true,
        relax_column_count: true,
      });
      if (records.length === 0) return { headers: [], rows: [] };
      const headers = records[0];
      const rows = records.slice(1, 1 + maxRows);
      return { headers, rows };
    },

    path_exists: (params) => fs.existsSync(String(params?.path ?? "")),

    set_always_on_top: (params) => {
      getWindow()?.setAlwaysOnTop(Boolean(params?.enabled));
      return null;
    },

    set_theme: (params) => {
      const theme = String(params?.theme ?? "light");
      const isDark = theme === "dark";
      nativeTheme.themeSource = isDark ? "dark" : "light";
      const win = getWindow();
      win?.setTitleBarOverlay?.({
        color: isDark ? "#14181f" : "#f6f7f9",
        symbolColor: isDark ? "#e7ebf1" : "#1c2330",
        height: 40,
      });
      return null;
    },

    open_in_file_manager: (params) => {
      void shell.openPath(String(params?.path ?? ""));
      return null;
    },

    choose_directory: async () => {
      const win = getWindow();
      if (!win) return null;
      const result = await dialog.showOpenDialog(win, {
        properties: ["openDirectory"],
      });
      return result.canceled ? null : result.filePaths[0] ?? null;
    },

    choose_zip_file: async () => {
      const win = getWindow();
      if (!win) return null;
      const result = await dialog.showOpenDialog(win, {
        properties: ["openFile"],
        filters: [{ name: "Zip", extensions: ["zip"] }],
      });
      return result.canceled ? null : result.filePaths[0] ?? null;
    },

    spawn_backend: (params) => {
      const request = params?.request as SpawnRequest;
      if (!request || typeof request.program !== "string" || !Array.isArray(request.args)) {
        throw new Error("Invalid spawn request");
      }
      return supervisor.spawnBackend(request, emitLine, (pid, code) => {
        emit({ type: "child", event: "exit", child_id: pid, code });
      });
    },

    kill_backend: (params) => {
      supervisor.killBackend(Number(params?.childId ?? 0));
      return null;
    },

    bootstrap_runtime: (params) => {
      const uvPath = String(params?.uvPath ?? "");
      const requirements = String(params?.requirements ?? "");
      const pythonVersion = String(params?.pythonVersion ?? "3.11");
      const dataDir = String(params?.dataDir ?? ctx.defaultDataDir);
      if (!uvPath) throw new Error("uv is not available");
      startBootstrapRuntime({
        uvPath,
        requirements,
        pythonVersion,
        dataDir,
        emitResource: (id, status, detail) =>
          emit({ type: "resource", id, status, detail }),
        emitError: (code, title, detail, suggestion) =>
          emit({ type: "error", code, title, detail, suggestion }),
        logLine,
      });
      return null;
    },
  };
}
