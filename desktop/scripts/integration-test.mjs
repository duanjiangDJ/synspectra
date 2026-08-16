// Full-stack integration test: drives the desktop carrier directly.
// Usage: node integration-test.mjs <wsUrl> <token>
// 1. resolves backend paths  2. bootstraps the managed Python runtime via uv
// 3. runs run_metrics (preset other) on a 6-file temp corpus
// 4. waits for the task end event and verifies the output CSV
import { createRequire } from "node:module";
import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const WebSocket = require("ws");

const wsUrl = process.argv[2];
const token = process.argv[3];
if (!wsUrl || !token) {
  console.error("usage: node integration-test.mjs <wsUrl> <token>");
  process.exit(2);
}

const log = (...args) => console.log("[it]", ...args);

async function main() {
  const ws = await new Promise((resolve, reject) => {
    const socket = new WebSocket(wsUrl + "?token=" + encodeURIComponent(token));
    socket.on("open", () => resolve(socket));
    socket.on("error", reject);
  });

  let seq = 0;
  const pending = new Map();
  const rpc = (method, params) =>
    new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params, token }));
    });

  const waitForEvent = (predicate, timeoutMs, label) =>
    new Promise((resolve) => {
      let settled = false;
      let timer = null;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        ws.removeListener("message", onMessage);
        resolve(value);
      };
      const onMessage = (data) => {
        let message;
        try { message = JSON.parse(data.toString()); } catch { return; }
        if (message.type === "event" && message.stream === "backend://event") {
          let payload;
          try { payload = JSON.parse(message.line); } catch { return; }
          if (predicate(payload)) finish(payload);
        }
      };
      ws.on("message", onMessage);
      timer = setTimeout(() => {
        log("timeout waiting for", label);
        finish(null);
      }, timeoutMs);
    });

  ws.on("message", (data) => {
    let message;
    try { message = JSON.parse(data.toString()); } catch { return; }
    if (typeof message.id !== "number") return;
    const entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    if (message.ok) entry.resolve(message.result);
    else entry.reject(new Error((message.error && message.error.message) || "rpc failed"));
  });

  try {
    // 1. paths with the dev data dir
    const repoRoot = process.env.REPO_ROOT || path.resolve(import.meta.dirname, "..", "..");
    const dataDir = path.join(repoRoot, ".desktop-data");
    const paths = await rpc("backend_paths", { dataDir });
    log("backend_paths:", JSON.stringify({ venv_python: paths.venv_python, uv: paths.uv, run_metrics: paths.run_metrics, requirements_lock: paths.requirements_lock }));

    // 2. bootstrap the managed runtime (uv python install -> venv -> hashed pip install).
    // In dev mode backend_paths prefers the repo .venv, so the managed runtime is
    // addressed explicitly at <dataDir>/venv; the RPC reports progress via resource events.
    const managedPython =
      process.platform === "win32"
        ? path.join(dataDir, "venv", "Scripts", "python.exe")
        : path.join(dataDir, "venv", "bin", "python");
    const depsInstalled = [
      path.join(dataDir, "venv", "Lib", "site-packages", "stanza"),
      path.join(dataDir, "venv", "lib", "python3.11", "site-packages", "stanza"),
    ].some((candidate) => existsSync(candidate));
    if (!existsSync(managedPython) || !depsInstalled) {
      log("bootstrapping managed Python runtime (downloads Python 3.11 + deps)...");
      await rpc("bootstrap_runtime", {
        uvPath: paths.uv,
        requirements: paths.requirements_lock,
        pythonVersion: "3.11",
        dataDir,
      });
      const readyEvent = await waitForEvent(
        (payload) => payload.type === "resource" && payload.id === "python_runtime" && payload.status === "ready",
        30 * 60 * 1000,
        "python_runtime ready",
      );
      if (!readyEvent) throw new Error("python_runtime never became ready");
      log("runtime ready:", readyEvent.detail);
    } else {
      log("managed runtime already present:", managedPython);
    }
    if (!existsSync(managedPython)) throw new Error("managed runtime missing after bootstrap");

    // 3. temp corpus
    const tmpRoot = mkdtempSync(path.join(tmpdir(), "synm-it-"));
    mkdirSync(path.join(tmpRoot, "src", "text"), { recursive: true });
    const sourceDir = path.join(repoRoot, "source", "text");
    for (let i = 1; i <= 6; i++) {
      cpSync(path.join(sourceDir, "text" + i + ".txt"), path.join(tmpRoot, "src", "text", "text" + i + ".txt"));
    }
    const resultDir = path.join(tmpRoot, "res");

    // 4. run the pipeline with the managed python
    const fresh = await rpc("backend_paths", { dataDir });
    const args = [
      fresh.run_metrics,
      "--preset", "other",
      "--source-dir", path.join(tmpRoot, "src"),
      "--result-dir", resultDir,
      "--no-resume",
      "--leo-model-folder", path.join(dataDir, "models"),
      "--log-format", "jsonl",
    ];
    log("spawning:", managedPython, args.join(" "));
    const childId = await rpc("spawn_backend", {
      request: { program: managedPython, args, env: { ...(fresh.env || {}), PYTHONUTF8: "1" } },
    });
    log("childId:", childId);
    const taskEnd = await waitForEvent(
      (payload) => payload.type === "task" && payload.event === "end",
      15 * 60 * 1000,
      "task end",
    );
    if (!taskEnd) throw new Error("pipeline never finished");
    log("task end:", JSON.stringify(taskEnd));
    if (taskEnd.status !== "success") throw new Error("pipeline status: " + taskEnd.status);

    const output = path.join(resultDir, "text.csv");
    if (!existsSync(output)) throw new Error("output CSV missing: " + output);
    log("output CSV exists:", output);
    rmSync(tmpRoot, { recursive: true, force: true });
    log("PASS");
    process.exitCode = 0;
  } catch (err) {
    log("FAIL:", String((err && err.stack) || err));
    process.exitCode = 1;
  } finally {
    ws.close();
  }
}

main();
