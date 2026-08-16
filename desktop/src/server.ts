import * as fs from "fs";
import * as http from "http";
import * as path from "path";
import { URL } from "url";
import { WebSocketServer, WebSocket } from "ws";

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".map": "application/json",
  ".txt": "text/plain; charset=utf-8",
};

export interface CarrierServerOptions {
  token: string;
  appDistDir: string | null;
  bootPayload: () => Record<string, unknown>;
  onRequest: (method: string, params: Record<string, unknown>) => Promise<unknown> | unknown;
}

export interface CarrierServer {
  port: number;
  host: string;
  broadcast: (stream: string, line: string) => void;
  close: () => Promise<void>;
}

function safeJson(value: unknown): string {
  // Prevent "</script>" inside the injected payload from closing the tag.
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

function injectBoot(html: string, nonce: string, bootPayload: () => Record<string, unknown>): string {
  const openTag = "<script nonce=\"";
  const script =
    openTag + nonce + "\">window.__SYNM_BOOT__ = " + safeJson(bootPayload()) + ";</script>";
  if (html.includes("</head>")) {
    return html.replace("</head>", script + "</head>");
  }
  return script + html;
}

export async function startCarrierServer(options: CarrierServerOptions): Promise<CarrierServer> {
  const clients = new Set<WebSocket>();
  const broadcast = (stream: string, line: string): void => {
    const payload = JSON.stringify({ type: "event", stream, line });
    for (const client of clients) {
      if (client.readyState === WebSocket.OPEN) client.send(payload);
    }
  };

  const server = http.createServer((req, res) => {
    void (async () => {
      try {
        const requestUrl = new URL(req.url ?? "/", "http://127.0.0.1");
        const pathname = decodeURIComponent(requestUrl.pathname);
        if (!options.appDistDir) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("carrier only (dev mode)");
          return;
        }
        const appDistDir = path.resolve(options.appDistDir);
        const indexPath = path.join(appDistDir, "index.html");
        const filePath = pathname === "/" ? indexPath : path.join(appDistDir, pathname);
        if (!filePath.startsWith(appDistDir + path.sep) && filePath !== indexPath) {
          res.writeHead(403, { "Content-Type": "text/plain" });
          res.end("forbidden");
          return;
        }
        if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("not found");
          return;
        }
        const ext = path.extname(filePath).toLowerCase();
        const contentType = MIME[ext] ?? "application/octet-stream";
        let body = fs.readFileSync(filePath);
        if (ext === ".html") {
          const nonce = require("crypto").randomBytes(16).toString("base64");
          const q = "'";
          const csp = [
            "default-src " + q + "self" + q,
            "script-src " + q + "self" + q + " " + q + "nonce-" + nonce + q,
            "style-src " + q + "self" + q + " " + q + "unsafe-inline" + q,
            "img-src " + q + "self" + q + " data:",
            "font-src " + q + "self" + q + " data:",
            "connect-src " + q + "self" + q + " ws://127.0.0.1:* ws://localhost:*",
            "object-src " + q + "none" + q,
            "base-uri " + q + "self" + q,
            "form-action " + q + "self" + q,
          ].join("; ");
          res.setHeader("Content-Security-Policy", csp);
          body = Buffer.from(injectBoot(body.toString("utf8"), nonce, options.bootPayload), "utf8");
        }
        res.writeHead(200, { "Content-Type": contentType, "Cache-Control": "no-cache" });
        res.end(body);
      } catch (err) {
        res.writeHead(500, { "Content-Type": "text/plain" });
        res.end(err instanceof Error ? err.message : "internal error");
      }
    })();
  });

  const wss = new WebSocketServer({ noServer: true });
  server.on("upgrade", (req, socket, head) => {
    const requestUrl = new URL(req.url ?? "/", "http://127.0.0.1");
    if (requestUrl.pathname !== "/carrier" || requestUrl.searchParams.get("token") !== options.token) {
      socket.write("HTTP/1.1 403 Forbidden\r\n\r\n");
      socket.destroy();
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => {
      clients.add(ws);
      ws.on("close", () => clients.delete(ws));
      ws.on("message", (data) => {
        let message: { id?: number; method?: string; params?: Record<string, unknown> };
        try {
          message = JSON.parse(String(data)) as typeof message;
        } catch {
          return;
        }
        if (typeof message.id !== "number" || typeof message.method !== "string") return;
        void Promise.resolve()
          .then(() => options.onRequest(message.method as string, message.params ?? {}))
          .then((result) => {
            ws.send(JSON.stringify({ id: message.id, ok: true, result: result ?? null }));
          })
          .catch((err: unknown) => {
            const detail = err instanceof Error ? err.message : String(err);
            ws.send(
              JSON.stringify({
                id: message.id,
                ok: false,
                error: { code: "RPC_FAILED", message: detail },
              }),
            );
          });
      });
    });
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve());
  });
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;

  return {
    port,
    host: "127.0.0.1",
    broadcast,
    close: async () => {
      for (const client of clients) client.close();
      await new Promise<void>((resolve) => wss.close(() => resolve()));
      await new Promise<void>((resolve) => server.close(() => resolve()));
    },
  };
}
