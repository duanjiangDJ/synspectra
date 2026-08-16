import { spawn } from "child_process";
import { createInterface } from "readline";
import * as fs from "fs";
import * as path from "path";

export interface BootstrapOptions {
  uvPath: string;
  requirements: string;
  pythonVersion: string;
  dataDir: string;
  emitResource: (id: string, status: string, detail: string) => void;
  emitError: (code: string, title: string, detail: string, suggestion: string) => void;
  logLine: (level: string, message: string) => void;
}

function runUv(
  uvPath: string,
  args: string[],
  env: Record<string, string>,
  logLine: (level: string, message: string) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(uvPath, args, {
      env: { ...process.env, ...env },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const read = (stream: NodeJS.ReadableStream | null, level: string) => {
      if (!stream) return;
      const reader = createInterface({ input: stream, crlfDelay: Infinity });
      reader.on("line", (line) => logLine(level, line));
    };
    read(child.stdout, "info");
    read(child.stderr, "warning");
    child.on("error", (err) => reject(err));
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error("uv exited with code " + String(code)));
      }
    });
  });
}

/**
 * Bootstraps the managed Python runtime with uv, mirroring the former Tauri
 * implementation: uv python install -> uv venv -> uv pip install (hashes).
 * Progress is reported through resource events on the python_runtime id.
 */
export function startBootstrapRuntime(options: BootstrapOptions): void {
  const { uvPath, requirements, pythonVersion, dataDir } = options;
  const runtimeDir = path.join(dataDir, "runtime");
  const cacheDir = path.join(dataDir, "uv-cache");
  const venvDir = path.join(dataDir, "venv");
  const pythonRel = process.platform === "win32" ? "Scripts/python.exe" : "bin/python";
  const venvPython = path.join(venvDir, pythonRel);

  // A venv with a python.exe but no installed dependencies is a half-built
  // runtime; require at least one known package before declaring ready.
  const depsInstalled = [
    path.join(venvDir, "Lib", "site-packages", "stanza"),
    path.join(venvDir, "lib", "python3.11", "site-packages", "stanza"),
  ].some((candidate) => fs.existsSync(candidate));

  if (fs.existsSync(venvPython) && depsInstalled) {
    options.emitResource("python_runtime", "ready", venvPython);
    return;
  }

  const hasVenv = fs.existsSync(venvPython);
  fs.mkdirSync(runtimeDir, { recursive: true });
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.mkdirSync(venvDir, { recursive: true });

  const env: Record<string, string> = {
    UV_PYTHON_INSTALL_DIR: runtimeDir,
    UV_CACHE_DIR: cacheDir,
    UV_DEFAULT_INDEX: "https://pypi.org/simple",
    PYTHONUTF8: "1",
  };

  void (async () => {
    try {
      if (!hasVenv) {
        options.emitResource("python_runtime", "downloading", "Downloading managed Python");
        await runUv(uvPath, ["python", "install", pythonVersion], env, options.logLine);
        options.emitResource("python_runtime", "installing", "Creating virtual environment");
        await runUv(uvPath, ["venv", "--python", pythonVersion, venvDir], env, options.logLine);
      }
      options.emitResource("python_runtime", "installing", "Installing Python dependencies");
      await runUv(
        uvPath,
        [
          "pip",
          "install",
          "--python",
          venvPython,
          "--require-hashes",
          "-r",
          requirements,
          // torch CPU wheels are only published on the PyTorch CPU index.
          "--extra-index-url",
          "https://download.pytorch.org/whl/cpu",
        ],
        env,
        options.logLine,
      );
      options.emitResource("python_runtime", "ready", venvPython);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      options.emitError(
        "BOOTSTRAP_FAILED",
        message,
        "",
        "Check the network connection and uv logs.",
      );
    }
  })();
}
