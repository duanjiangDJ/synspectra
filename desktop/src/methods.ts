import { parse } from "csv-parse/sync";
import { dialog, nativeTheme, shell, type BrowserWindow } from "electron";
import * as fs from "fs";
import * as path from "path";
import * as zlib from "zlib";

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

function decodeXmlEntities(text: string): string {
  return text.replace(
    /&(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);/g,
    (_, entity: string) => {
      if (entity === "amp") return "&";
      if (entity === "lt") return "<";
      if (entity === "gt") return ">";
      if (entity === "quot") return '"';
      if (entity === "apos") return "'";
      if (entity.startsWith("#x")) return String.fromCodePoint(parseInt(entity.slice(2), 16));
      if (entity.startsWith("#")) return String.fromCodePoint(parseInt(entity.slice(1), 10));
      return `&${entity};`;
    },
  );
}

function colIndexFromRef(ref: string): number {
  let idx = 0;
  for (let i = 0; i < ref.length; i++) {
    const code = ref.charCodeAt(i);
    if (code >= 65 && code <= 90) {
      idx = idx * 26 + (code - 64);
    } else if (code >= 97 && code <= 122) {
      idx = idx * 26 + (code - 96);
    } else {
      break;
    }
  }
  return idx > 0 ? idx - 1 : -1;
}

function readZipEntries(buf: Buffer, targets: Set<string>): Map<string, Buffer> {
  const out = new Map<string, Buffer>();
  const minOffset = Math.max(0, buf.length - 65558);
  let eocd = -1;
  for (let i = buf.length - 22; i >= minOffset; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) return out;

  const totalEntries = buf.readUInt16LE(eocd + 10);
  let pos = buf.readUInt32LE(eocd + 16);
  for (let i = 0; i < totalEntries && pos + 46 <= eocd; i++) {
    if (buf.readUInt32LE(pos) !== 0x02014b50) break;
    const compMethod = buf.readUInt16LE(pos + 10);
    const compSize = buf.readUInt32LE(pos + 20);
    const nameLen = buf.readUInt16LE(pos + 28);
    const extraLen = buf.readUInt16LE(pos + 30);
    const commentLen = buf.readUInt16LE(pos + 32);
    const localOffset = buf.readUInt32LE(pos + 42);
    const name = buf.toString("utf8", pos + 46, pos + 46 + nameLen);
    pos += 46 + nameLen + extraLen + commentLen;

    if (!targets.has(name) || localOffset + 30 > buf.length) continue;
    const lhNameLen = buf.readUInt16LE(localOffset + 26);
    const lhExtraLen = buf.readUInt16LE(localOffset + 28);
    const dataStart = localOffset + 30 + lhNameLen + lhExtraLen;
    const raw = buf.subarray(dataStart, dataStart + compSize);
    if (compMethod === 0) {
      out.set(name, raw);
    } else if (compMethod === 8) {
      out.set(name, zlib.inflateRawSync(raw));
    }
  }
  return out;
}

function readXlsxPreview(xlsxPath: string, maxRows: number): { headers: string[]; rows: string[][] } {
  const buf = fs.readFileSync(xlsxPath);
  const metaEntries = readZipEntries(
    buf,
    new Set(["xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/sharedStrings.xml"]),
  );

  let firstSheetPath = "xl/worksheets/sheet1.xml";
  const wbBuf = metaEntries.get("xl/workbook.xml");
  const relsBuf = metaEntries.get("xl/_rels/workbook.xml.rels");
  if (wbBuf && relsBuf) {
    const wbXml = wbBuf.toString("utf8");
    const relsXml = relsBuf.toString("utf8");
    const firstSheet = wbXml.match(/<sheet\b[^>]*\b(?:r:)?id="([^"]+)"/);
    if (firstSheet) {
      const relId = firstSheet[1];
      const relRe = /<Relationship\b([^>]+)\/?>/g;
      let relMatch: RegExpExecArray | null;
      while ((relMatch = relRe.exec(relsXml))) {
        const attrs = relMatch[1];
        const idMatch = attrs.match(/\bId="([^"]+)"/);
        const targetMatch = attrs.match(/\bTarget="([^"]+)"/);
        if (idMatch?.[1] === relId && targetMatch?.[1]) {
          const cleaned = targetMatch[1].replace(/^\/+/, "");
          firstSheetPath = cleaned.startsWith("xl/") ? cleaned : `xl/${cleaned}`;
          break;
        }
      }
    }
  }

  const sheetEntries = readZipEntries(buf, new Set([firstSheetPath]));
  const sheetBuf = sheetEntries.get(firstSheetPath);
  if (!sheetBuf) return { headers: [], rows: [] };

  const sharedStrings: string[] = [];
  const ssBuf = metaEntries.get("xl/sharedStrings.xml");
  if (ssBuf) {
    const ssXml = ssBuf.toString("utf8");
    const siRe = /<si\b[^>]*>([\s\S]*?)<\/si>/g;
    let siMatch: RegExpExecArray | null;
    while ((siMatch = siRe.exec(ssXml))) {
      const tRe = /<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g;
      let tMatch: RegExpExecArray | null;
      let combined = "";
      while ((tMatch = tRe.exec(siMatch[1]))) {
        combined += decodeXmlEntities(tMatch[1]);
      }
      sharedStrings.push(combined);
    }
  }

  const sheetXml = sheetBuf.toString("utf8");
  const parsedRows: string[][] = [];
  const rowRe = /<row\b[^>]*>([\s\S]*?)<\/row>/g;
  const cellRe = /<c\b([^>]*)(?:\/>|>([\s\S]*?)<\/c>)/g;
  let rowMatch: RegExpExecArray | null;
  while ((rowMatch = rowRe.exec(sheetXml)) && parsedRows.length < 1 + maxRows) {
    const rowValues: string[] = [];
    cellRe.lastIndex = 0;
    let cellMatch: RegExpExecArray | null;
    while ((cellMatch = cellRe.exec(rowMatch[1]))) {
      const attrs = cellMatch[1];
      const body = cellMatch[2] ?? "";
      const refMatch = attrs.match(/\br="([^"]+)"/);
      let colIdx = refMatch ? colIndexFromRef(refMatch[1]) : -1;
      if (colIdx < 0) colIdx = rowValues.length;
      while (rowValues.length <= colIdx) rowValues.push("");

      const typeMatch = attrs.match(/\bt="([^"]*)"/);
      const cellType = typeMatch ? typeMatch[1] : "";
      let value = "";
      if (cellType === "inlineStr") {
        const tRe = /<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g;
        let tMatch: RegExpExecArray | null;
        while ((tMatch = tRe.exec(body))) {
          value += decodeXmlEntities(tMatch[1]);
        }
      } else {
        const vMatch = body.match(/<v>([\s\S]*?)<\/v>/);
        const rawVal = vMatch ? decodeXmlEntities(vMatch[1]) : "";
        if (cellType === "s" && rawVal !== "") {
          const ssIndex = Number(rawVal);
          value = Number.isInteger(ssIndex) && sharedStrings[ssIndex] !== undefined
            ? sharedStrings[ssIndex]
            : rawVal;
        } else {
          value = rawVal;
        }
      }
      rowValues[colIdx] = value;
    }
    parsedRows.push(rowValues);
  }

  if (parsedRows.length === 0) return { headers: [], rows: [] };
  const headers = parsedRows[0];
  const rows = parsedRows.slice(1, 1 + maxRows).map((row) => {
    if (row.length >= headers.length) return row;
    return [...row, ...Array<string>(headers.length - row.length).fill("")];
  });
  return { headers, rows };
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
        .filter((entry) => {
          if (!entry.isFile()) return false;
          const lower = entry.name.toLowerCase();
          if (entry.name.startsWith("~$") || lower.endsWith(".tmp")) return false;
          return lower.endsWith(".xlsx") || lower.endsWith(".csv");
        })
        .map((entry) => entry.name)
        .sort();
    },

    read_csv_preview: (params) => {
      const filePath = String(params?.path ?? "");
      const maxRows = Math.min(Number(params?.maxRows ?? 100) || 100, 500);
      if (filePath.toLowerCase().endsWith(".xlsx")) {
        return readXlsxPreview(filePath, maxRows);
      }
      const content = fs.readFileSync(filePath, "utf8");
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
