import { spawn, spawnSync, type ChildProcess } from "child_process";
import { createInterface } from "readline";

export interface SpawnRequest {
  program: string;
  args: string[];
  env: Record<string, string>;
}

export type LineSink = (stream: string, line: string) => void;
export type ExitSink = (pid: number, code: number | null) => void;

function pipeLines(stream: NodeJS.ReadableStream | null, eventStream: string, sink: LineSink): void {
  if (!stream) return;
  const reader = createInterface({ input: stream, crlfDelay: Infinity });
  reader.on("line", (line) => {
    sink(eventStream, line);
    if (eventStream !== "backend://raw") sink("backend://raw", line);
  });
}

/** Tracks backend child processes and forwards their output line by line. */
export class Supervisor {
  private children = new Map<number, ChildProcess>();

  spawnBackend(request: SpawnRequest, sink: LineSink, onExit?: ExitSink): number {
    const child = spawn(request.program, request.args, {
      env: { ...process.env, ...request.env },
      windowsHide: true,
      // POSIX: new process group so killBackend can take down the whole tree
      // (including grandchildren such as the NeoSCA JVM).
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    });
    const pid = child.pid;
    if (pid !== undefined) this.children.set(pid, child);
    child.on("exit", (code) => {
      if (pid !== undefined) {
        this.children.delete(pid);
        onExit?.(pid, code);
      }
    });
    child.on("error", (err) => {
      sink("backend://stderr", "spawn error: " + err.message);
      sink("backend://raw", "spawn error: " + err.message);
      if (pid !== undefined) {
        this.children.delete(pid);
        onExit?.(pid, null);
      }
    });
    pipeLines(child.stdout, "backend://event", sink);
    pipeLines(child.stderr, "backend://stderr", sink);
    return pid ?? 0;
  }

  killBackend(childId: number): void {
    const child = this.children.get(childId);
    if (!child) return;
    this.children.delete(childId);
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/PID", String(childId), "/T", "/F"], { windowsHide: true });
    } else {
      try {
        process.kill(-childId, "SIGKILL");
      } catch {
        /* already gone */
      }
      try {
        child.kill("SIGKILL");
      } catch {
        /* already gone */
      }
    }
  }

  killAll(): void {
    for (const childId of [...this.children.keys()]) {
      this.killBackend(childId);
    }
  }
}
