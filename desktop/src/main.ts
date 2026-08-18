import { randomBytes } from "crypto";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import { app, BrowserWindow, Menu, shell } from "electron";

import { E2E_SCRIPT } from "./e2e";
import { installScript } from "./e2e-install";
import { createMethodHandlers } from "./methods";
import { findRepoRoot, resolveBackendPaths, uvName, type DesktopContext } from "./paths";
import { startCarrierServer, type CarrierServer } from "./server";
import { Supervisor } from "./supervisor";

const argv = new Set(process.argv.slice(1));
const isSmoke = argv.has("--smoke");
const isE2e = argv.has("--e2e");
const isE2eInstall = argv.has("--e2e-install");
const isHeadless = argv.has("--headless");
const devUrl = process.env.SYN_METRICS_DEV_URL || null;
const screenshotPath = (() => {
  const index = process.argv.indexOf("--screenshot");
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : null;
})();

let mainWindow: BrowserWindow | null = null;
let carrier: CarrierServer | null = null;
let activeToken = "";
let activeContext: DesktopContext | null = null;
const supervisor = new Supervisor();

function buildContext(): DesktopContext {
  const packaged = app.isPackaged;
  const repoRoot = packaged ? null : findRepoRoot(process.cwd());
  const backendRoot = packaged
    ? path.join(process.resourcesPath, "backend")
    : repoRoot ?? process.cwd();
  const appDistDir = packaged
    ? path.join(process.resourcesPath, "app-dist")
    : repoRoot
      ? path.join(repoRoot, "app", "dist")
      : null;
  const repoUv = repoRoot
    ? (() => {
        const candidate = path.join(
          repoRoot,
          ".venv",
          process.platform === "win32" ? "Scripts" : "bin",
          uvName(),
        );
        return fs.existsSync(candidate) ? candidate : null;
      })()
    : null;
  const uvPath =
    repoUv ?? (packaged ? path.join(process.resourcesPath, "bin", uvName()) : null);
  const defaultDataDir = packaged
    ? path.dirname(process.execPath)
    : repoRoot
      ? path.join(repoRoot, ".desktop-data")
      : path.join(os.homedir(), ".syntactic-metrics-data");
  return { packaged, backendRoot, appDistDir, uvPath, defaultDataDir };
}

function bootPayload(ctx: DesktopContext, token: string): Record<string, unknown> {
  return {
    env: "desktop",
    platform: process.platform,
    wsUrl: "ws://127.0.0.1:" + String(carrier?.port ?? 0) + "/carrier",
    token,
    paths: resolveBackendPaths(ctx, undefined),
  };
}

function devBootScript(payload: Record<string, unknown>): string {
  const json = JSON.stringify(payload).replace(/</g, "\\u003c");
  return (
    "window.__SYNM_BOOT__ = " +
    json +
    "; window.dispatchEvent(new CustomEvent(\"synm:boot\"));"
  );
}

const SMOKE_SCRIPT = `
(() => {
  const boot = window.__SYNM_BOOT__;
  if (!boot) return Promise.resolve({ ok: false, reason: "boot object missing" });
  if (!boot.paths) return Promise.resolve({ ok: false, reason: "boot paths missing" });
  const ws = new WebSocket(boot.wsUrl + "?token=" + encodeURIComponent(boot.token));
  return new Promise((resolve) => {
    ws.onopen = () => {
      ws.send(JSON.stringify({ id: 1, method: "path_exists", params: { path: boot.paths.data_dir }, token: boot.token }));
    };
    ws.onmessage = (event) => {
      let response;
      try { response = JSON.parse(event.data); } catch (err) { resolve({ ok: false, reason: String(err) }); return; }
      ws.close();
      resolve({
        ok: response.ok === true && response.result === true,
        platform: boot.platform,
        env: boot.env,
        dataDir: boot.paths.data_dir,
        rpc: response,
        ui: {
          shell: !!document.querySelector(".app-shell"),
          tabs: document.querySelectorAll(".tabbar .tab").length,
          heading: (document.querySelector(".page-section h2") || {}).textContent || null,
        },
      });
    };
    ws.onerror = () => resolve({ ok: false, reason: "carrier websocket error" });
  });
})()
`;

function guardNavigation(win: BrowserWindow, allowedOrigin: string): void {
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(allowedOrigin)) {
      event.preventDefault();
      if (/^https?:/i.test(url)) void shell.openExternal(url);
    }
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
}

function createWindow(ctx: DesktopContext, token: string): BrowserWindow {
  // DSHD advanced-shell style frame: no native title bar; the OS caption
  // buttons (min/max/close) are overlaid on the top-right (Windows/Linux)
  // or shown as traffic lights (macOS). The web app owns a drag strip below.
  const frameOptions: Record<string, unknown> =
    process.platform === "darwin"
      ? {
          titleBarStyle: "hiddenInset",
          trafficLightPosition: { x: 14, y: 12 },
        }
      : {
          titleBarStyle: "hidden",
          titleBarOverlay: {
            color: "#f6f7f9",
            symbolColor: "#1c2330",
            height: 40,
          },
        };
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 900,
    minHeight: 620,
    show: !isSmoke && !isE2e && !isE2eInstall && !screenshotPath,
    autoHideMenuBar: true,
    backgroundColor: "#f6f7f9",
    title: "SynSpectra",
    ...frameOptions,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });
  mainWindow = win;
  const origin = devUrl ?? "http://127.0.0.1:" + String(carrier?.port ?? 0);
  guardNavigation(win, origin);
  if (devUrl) {
    win.webContents.on("did-finish-load", () => {
      void win.webContents
        .executeJavaScript(devBootScript(bootPayload(ctx, token)))
        .catch((err: unknown) => console.error("[boot] injection failed:", err));
    });
  }
  void win.loadURL(origin);
  win.on("closed", () => {
    if (mainWindow === win) mainWindow = null;
  });
  return win;
}

function runInstallE2e(win: BrowserWindow): void {
  const dataDir = activeContext
    ? activeContext.defaultDataDir + "-e2e"
    : path.join(os.homedir(), ".syntactic-metrics-data-e2e");
  const script = installScript(dataDir);
  console.log("E2E_INSTALL dataDir=" + dataDir);
  let finished = false;
  const timeout = setTimeout(() => {
    if (finished) return;
    console.log("E2E_INSTALL_RESULT " + JSON.stringify({ ok: false, reason: "timeout" }));
    app.exit(2);
  }, 45 * 60 * 1000);
  win.webContents.on("did-finish-load", () => {
    setTimeout(() => {
      void win.webContents
        .executeJavaScript(script, true)
        .then((result: unknown) => {
          const value = result as { ok?: boolean; reloading?: boolean };
          if (value?.reloading) return; // page reloaded; script re-runs on the next load
          finished = true;
          console.log("E2E_INSTALL_RESULT " + JSON.stringify(result));
          clearTimeout(timeout);
          app.exit(value?.ok === true ? 0 : 1);
        })
        .catch((err: unknown) => {
          if (finished) return;
          finished = true;
          console.log("E2E_INSTALL_RESULT " + JSON.stringify({ ok: false, reason: String(err) }));
          clearTimeout(timeout);
          app.exit(1);
        });
    }, 2500);
  });
}

function runScreenshot(win: BrowserWindow, outputPath: string): void {
  let done = false;
  const timeout = setTimeout(() => {
    if (done) return;
    done = true;
    console.log("SCREENSHOT_TIMEOUT");
    app.exit(2);
  }, 20000);
  win.webContents.once("did-finish-load", () => {
    setTimeout(() => {
      void win.webContents
        .capturePage()
        .then((image) => {
          done = true;
          clearTimeout(timeout);
          fs.writeFileSync(outputPath, image.toPNG());
          console.log("SCREENSHOT_SAVED " + outputPath);
          app.exit(0);
        })
        .catch((err: unknown) => {
          done = true;
          clearTimeout(timeout);
          console.log("SCREENSHOT_FAILED " + String(err));
          app.exit(1);
        });
    }, 3000);
  });
}

function runE2e(win: BrowserWindow): void {
  win.webContents.on("console-message", (_event, levelOrDetails, ...rest) => {
    const message =
      typeof levelOrDetails === "object" && levelOrDetails !== null
        ? String((levelOrDetails as { message?: unknown }).message ?? "")
        : String(rest[0] ?? "");
    console.log("RENDERER", message);
  });
  const timeout = setTimeout(() => {
    console.log("E2E_RESULT " + JSON.stringify({ ok: false, reason: "timeout" }));
    app.exit(2);
  }, 60000);
  win.webContents.once("did-finish-load", () => {
    setTimeout(() => {
      void win.webContents
        .executeJavaScript(E2E_SCRIPT, true)
        .then((result: unknown) => {
          console.log("E2E_RESULT " + JSON.stringify(result));
          clearTimeout(timeout);
          const ok =
            typeof result === "object" &&
            result !== null &&
            (result as { ok?: boolean }).ok === true;
          app.exit(ok ? 0 : 1);
        })
        .catch((err: unknown) => {
          console.log("E2E_RESULT " + JSON.stringify({ ok: false, reason: String(err) }));
          clearTimeout(timeout);
          app.exit(1);
        });
    }, 2500);
  });
}

function runSmoke(win: BrowserWindow): void {
  const timeout = setTimeout(() => {
    console.log("SMOKE_RESULT " + JSON.stringify({ ok: false, reason: "timeout" }));
    app.exit(2);
  }, 30000);
  win.webContents.once("did-finish-load", () => {
    setTimeout(() => {
      void win.webContents
        .executeJavaScript(SMOKE_SCRIPT, true)
        .then((result: unknown) => {
          console.log("SMOKE_RESULT " + JSON.stringify(result));
          clearTimeout(timeout);
          const ok =
            typeof result === "object" &&
            result !== null &&
            (result as { ok?: boolean }).ok === true;
          app.exit(ok ? 0 : 1);
        })
        .catch((err: unknown) => {
          console.log("SMOKE_RESULT " + JSON.stringify({ ok: false, reason: String(err) }));
          clearTimeout(timeout);
          app.exit(1);
        });
    }, 2500);
  });
}

async function runApp(): Promise<void> {
  const ctx = buildContext();
  const token = randomBytes(16).toString("hex");
  activeContext = ctx;
  activeToken = token;

  const emit = (payload: Record<string, unknown>): void => {
    carrier?.broadcast("backend://event", JSON.stringify(payload));
  };
  // Child stdout/stderr lines keep their own stream; broadcast wraps the
  // envelope once. emit() above is only for shell-generated JSON events.
  const emitLine = (stream: string, line: string): void => {
    carrier?.broadcast(stream, line);
  };
  const logLine = (level: string, message: string): void => {
    emit({ type: "log", level, message });
  };
  const handlers = createMethodHandlers({
    ctx,
    supervisor,
    getWindow: () => mainWindow,
    emit,
    emitLine,
    logLine,
  });

  carrier = await startCarrierServer({
    token,
    appDistDir: devUrl ? null : ctx.appDistDir,
    bootPayload: () => bootPayload(ctx, token),
    onRequest: async (method, params) => {
      const handler = handlers[method];
      if (!handler) throw new Error("Unknown RPC method: " + method);
      return handler(params);
    },
  });

  if (isHeadless) {
    console.log(
      "HEADLESS_READY http://127.0.0.1:" +
        carrier.port +
        " ws://127.0.0.1:" +
        carrier.port +
        "/carrier token=" +
        token,
    );
    return;
  }

  const win = createWindow(ctx, token);
  if (isSmoke) runSmoke(win);
  if (isE2e) runE2e(win);
  if (isE2eInstall) runInstallE2e(win);
  if (screenshotPath) runScreenshot(win, screenshotPath);
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.on("window-all-closed", () => {
    if (!isHeadless && process.platform !== "darwin") app.quit();
  });

  app.on("activate", () => {
    if (!mainWindow && carrier && activeContext) {
      createWindow(activeContext, activeToken);
    }
  });

  app.on("before-quit", () => {
    supervisor.killAll();
    void carrier?.close();
  });

  void app.whenReady().then(() => {
    if (process.platform !== "darwin") Menu.setApplicationMenu(null);
    return runApp();
  });
}
