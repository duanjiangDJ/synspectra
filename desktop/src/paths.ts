import * as fs from "fs";
import * as path from "path";

export interface BackendPaths {
  repo_root: string | null;
  default_data_dir: string;
  data_dir: string;
  venv_python: string | null;
  uv: string | null;
  run_metrics: string | null;
  resource_manager: string | null;
  corpus_import: string | null;
  manifest: string | null;
  requirements_lock: string | null;
  env: Record<string, string>;
}

export interface DesktopContext {
  packaged: boolean;
  backendRoot: string;
  appDistDir: string | null;
  uvPath: string | null;
  defaultDataDir: string;
}

export function pythonRel(): string {
  return process.platform === "win32" ? "Scripts/python.exe" : "bin/python";
}

export function uvName(): string {
  return process.platform === "win32" ? "uv.exe" : "uv";
}

/** Walk up from startDir looking for the repository root (contains run_metrics.py). */
export function findRepoRoot(startDir: string): string | null {
  let dir = path.resolve(startDir);
  for (let depth = 0; depth < 20; depth++) {
    if (fs.existsSync(path.join(dir, "run_metrics.py"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
  return null;
}

export function resolveBackendPaths(
  ctx: DesktopContext,
  dataDirOverride?: string,
): BackendPaths {
  const dataDir = path.resolve(dataDirOverride || ctx.defaultDataDir);
  fs.mkdirSync(dataDir, { recursive: true });

  const repoUv = ctx.uvPath;
  const repoVenvPython = ctx.backendRoot && !ctx.packaged
    ? (() => {
        const candidate = path.join(ctx.backendRoot, ".venv", pythonRel());
        return fs.existsSync(candidate) ? candidate : null;
      })()
    : null;
  const packagedVenvPython = path.join(dataDir, "venv", pythonRel());
  const venvPython = repoVenvPython ?? (fs.existsSync(packagedVenvPython) ? packagedVenvPython : null);

  const stanzaDir = path.join(dataDir, "stanza_resources");
  const javaDir = path.join(dataDir, "java");
  const parserDir = path.join(dataDir, "stanford", "parser");
  const tregexDir = path.join(dataDir, "stanford", "tregex");

  const env: Record<string, string> = {};
  env.STANZA_RESOURCES_DIR = stanzaDir;
  if (fs.existsSync(javaDir)) {
    env.JAVA_HOME = javaDir;
    const javaBin = path.join(javaDir, "bin");
    if (fs.existsSync(javaBin)) {
      const sep = process.platform === "win32" ? ";" : ":";
      env.PATH = javaBin + sep + (process.env.PATH ?? "");
    }
  }
  if (fs.existsSync(parserDir)) env.STANFORD_PARSER_HOME = parserDir;
  if (fs.existsSync(tregexDir)) env.STANFORD_TREGEX_HOME = tregexDir;

  const backendRoot = ctx.backendRoot;
  return {
    // repo_root is the dev repository root; null inside a packaged install so
    // the UI falls back to portable (exe-adjacent) corpus/result locations.
    repo_root: ctx.packaged ? null : backendRoot,
    default_data_dir: ctx.defaultDataDir,
    data_dir: dataDir,
    venv_python: venvPython,
    uv: repoUv ?? (ctx.packaged ? path.join(process.resourcesPath, "bin", uvName()) : null),
    run_metrics: path.join(backendRoot, "run_metrics.py"),
    resource_manager: path.join(backendRoot, "scripts", "resource_manager.py"),
    corpus_import: path.join(backendRoot, "scripts", "corpus_import.py"),
    manifest: path.join(backendRoot, "resources", "resource_manifest.json"),
    requirements_lock: path.join(backendRoot, "requirements.lock"),
    env,
  };
}
