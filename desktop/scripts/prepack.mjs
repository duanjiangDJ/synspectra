import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const desktopDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const repoRoot = path.dirname(desktopDir);
const staging = path.join(desktopDir, "resources");

rmSync(staging, { recursive: true, force: true });

function copyPythonTree(src, dest) {
  cpSync(src, dest, {
    recursive: true,
    filter: (p) => !p.endsWith(".pyc") && !p.includes("__pycache__"),
  });
}

// 1. Python backend (run_metrics + metric_modules + needed scripts + manifest + lock)
const backend = path.join(staging, "backend");
mkdirSync(backend, { recursive: true });
cpSync(path.join(repoRoot, "run_metrics.py"), path.join(backend, "run_metrics.py"));
copyPythonTree(path.join(repoRoot, "metric_modules"), path.join(backend, "metric_modules"));
mkdirSync(path.join(backend, "scripts"), { recursive: true });
cpSync(path.join(repoRoot, "scripts", "corpus_import.py"), path.join(backend, "scripts", "corpus_import.py"));
cpSync(path.join(repoRoot, "scripts", "resource_manager.py"), path.join(backend, "scripts", "resource_manager.py"));
mkdirSync(path.join(backend, "resources"), { recursive: true });
cpSync(
  path.join(repoRoot, "resources", "resource_manifest.json"),
  path.join(backend, "resources", "resource_manifest.json"),
);
cpSync(path.join(repoRoot, "requirements.lock"), path.join(backend, "requirements.lock"));

// 2. Web app build
const appDist = path.join(repoRoot, "app", "dist");
if (!existsSync(path.join(appDist, "index.html"))) {
  throw new Error("app/dist is missing; run 'npm run build --workspace app' first");
}
cpSync(appDist, path.join(staging, "app-dist"), { recursive: true });

// 3. uv binary (bundled runtime installer)
const binDir = path.join(staging, "bin");
mkdirSync(binDir, { recursive: true });
const uvName = process.platform === "win32" ? "uv.exe" : "uv";
const candidates = [
  process.env.UV_BIN,
  path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts" : "bin", uvName),
].filter(Boolean);
let copied = false;
for (const src of candidates) {
  if (src && existsSync(src)) {
    cpSync(src, path.join(binDir, uvName));
    copied = true;
    break;
  }
}
if (!copied) {
  console.warn("[prepack] uv binary not found; the installer will lack a bundled uv");
}

console.log("[prepack] staged backend, app-dist and bin under", staging);
