// Structured console rendering: turns raw backend JSONL lines into
// human-readable, level-colored entries instead of dumping JSON.

export type ConsoleLevel = "info" | "warn" | "error" | "success" | "muted" | "plain";

export interface ConsoleEntry {
  id: number;
  level: ConsoleLevel;
  prefix: string;
  text: string;
}

export const STAGE_LABELS: Record<string, string> = {
  stanza: "Stanza",
  category: "Category",
  file: "File",
  custom: "Custom",
  leo: "LeoDD",
  quansyn: "QuanSyn",
  neosca: "NeoSCA",
  write: "Write",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

function trimTo(text: string, limit: number): string {
  return text.length > limit ? text.slice(0, limit - 1) + "…" : text;
}

function formatBytes(value: number): string {
  return (value / (1024 * 1024)).toFixed(1) + " MB";
}

interface RawEvent {
  type?: string;
  event?: string;
  status?: string;
  stage?: string;
  message?: string;
  level?: string;
  title?: string;
  detail?: string;
  suggestion?: string;
  code?: string;
  id?: string;
  file?: string;
  done?: number;
  total?: number;
  methods?: string[];
  bytes_done?: number;
  bytes_total?: number;
  child_id?: number;
  imported?: number;
  skipped?: number;
  label?: string;
}

const PREFIX: Record<ConsoleLevel, string> = {
  info: "·",
  warn: "⚠",
  error: "✗",
  success: "✓",
  muted: "–",
  plain: " ",
};

/** Formats one raw console line into a display entry (or null to skip). */
export function formatConsoleLine(line: string, id: number): ConsoleEntry {
  let event: RawEvent;
  try {
    event = JSON.parse(line) as RawEvent;
  } catch {
    return { id, level: "plain", prefix: " ", text: line };
  }

  const entry = (level: ConsoleLevel, text: string): ConsoleEntry => ({
    id,
    level,
    prefix: PREFIX[level],
    text,
  });

  switch (event.type) {
    case "task": {
      if (event.event === "start") {
        const methods = Array.isArray(event.methods) ? event.methods.join(",") : "";
        return entry("success", "Task started" + (methods ? " · methods: " + methods : ""));
      }
      if (event.event === "end") {
        return entry(
          event.status === "success" ? "success" : "error",
          "Task " + (event.status === "success" ? "finished" : "failed"),
        );
      }
      break;
    }
    case "stage": {
      const stage = event.stage ?? "";
      const label = stageLabel(stage);
      if (stage === "file") {
        const file = (event.message ?? "").split(":")[0] ?? "";
        return entry("info", "Processing " + file);
      }
      return entry("info", label + (event.message ? " — " + trimTo(event.message, 100) : ""));
    }
    case "progress": {
      const done = Number(event.done ?? 0);
      const total = Number(event.total ?? 0);
      const file = event.file ?? "";
      return entry(
        "success",
        done + "/" + total + "  " + file + "  (" + stageLabel(event.stage ?? "") + ")",
      );
    }
    case "log": {
      const level = event.level === "warning" ? "warn" : "muted";
      return entry(level, event.message ?? "");
    }
    case "error": {
      const parts = [event.title ?? "", event.detail ?? "", event.suggestion ?? ""]
        .map((part) => trimTo(part, 160))
        .filter((part) => part.length > 0);
      return entry("error", (event.code ? "[" + event.code + "] " : "") + parts.join(" — "));
    }
    case "resource": {
      const id = event.id ?? "";
      const status = event.status ?? "";
      if (status === "ready") {
        return entry("success", id + " ready");
      }
      if (status === "download_failed" || status === "install_failed") {
        return entry("error", id + " " + status + (event.detail ? " — " + trimTo(event.detail, 160) : ""));
      }
      if (status === "downloading") {
        const hasBytes =
          typeof event.bytes_done === "number" && typeof event.bytes_total === "number";
        return entry(
          "info",
          "Downloading " + id + (hasBytes ? " " + formatBytes(event.bytes_done ?? 0) + " / " + formatBytes(event.bytes_total ?? 0) : ""),
        );
      }
      return entry("info", id + " " + status + (event.detail ? " — " + trimTo(event.detail, 120) : ""));
    }
    case "child": {
      if (event.event === "exit") {
        const ok = event.status === undefined ? (Number(event.code ?? 0) === 0) : event.status !== "error";
        return entry(
          ok ? "muted" : "error",
          "Process #" + String(event.child_id ?? 0) + " exited (code " + String(event.code ?? "?") + ")",
        );
      }
      break;
    }
    case "corpus": {
      if (event.event === "scan") {
        return entry("info", "Corpus scan finished");
      }
      if (event.event === "done") {
        return entry(
          "success",
          "Imported " + String(event.imported ?? 0) + " file(s), skipped " + String(event.skipped ?? 0),
        );
      }
      if (event.event === "error") {
        return entry("error", "Corpus import failed: " + trimTo(String(event.detail ?? ""), 160));
      }
      if (event.event === "progress") {
        return entry("info", "Importing " + String(event.done ?? 0) + "/" + String(event.total ?? 0));
      }
      break;
    }
  }

  // Unknown structured event: compact, single-line JSON in muted style.
  const compact = JSON.stringify(event);
  return entry("muted", trimTo(compact, 240));
}
