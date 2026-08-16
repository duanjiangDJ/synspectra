import { writable } from "svelte/store";

import { Carrier } from "./carrier";
import type { BackendPaths, RpcMethod, RpcMethods } from "./contracts";
import { BOOT_EVENT, resolveBootTarget } from "./boot";

export type BridgeKind = "rpc" | "mock" | null;

export interface BackendBridge {
  readonly kind: "rpc" | "mock";
  readonly paths: BackendPaths | null;
  available(): boolean;
  request<T extends RpcMethod>(method: T, params: RpcMethods[T]["params"]): Promise<RpcMethods[T]["result"]>;
  dispose(): void;
}

/** Stable event bus: subscriptions survive bridge swaps (e.g. late boot in dev mode). */
const bus = new Map<string, Set<(line: string) => void>>();

export function onBus(stream: string, callback: (line: string) => void): () => void {
  let callbacks = bus.get(stream);
  if (!callbacks) {
    callbacks = new Set();
    bus.set(stream, callbacks);
  }
  callbacks.add(callback);
  return () => {
    callbacks?.delete(callback);
  };
}

class RpcBridge implements BackendBridge {
  readonly kind = "rpc" as const;
  readonly paths: BackendPaths | null;
  private offs: Array<() => void> = [];

  constructor(
    private readonly carrier: Carrier,
    paths: BackendPaths | null,
  ) {
    this.paths = paths;
    for (const stream of ["backend://event", "backend://raw", "backend://stderr"]) {
      this.offs.push(
        carrier.on(stream, (line) => {
          const callbacks = bus.get(stream);
          if (callbacks) {
            for (const callback of [...callbacks]) callback(line);
          }
        }),
      );
    }
  }

  available(): boolean {
    return this.carrier.state === "connected";
  }

  request<T extends RpcMethod>(method: T, params: RpcMethods[T]["params"]): Promise<RpcMethods[T]["result"]> {
    return this.carrier.request<RpcMethods[T]["result"]>(method, params);
  }

  dispose(): void {
    for (const off of this.offs) off();
    this.offs = [];
    this.carrier.close();
  }
}

const MOCK_PATHS: BackendPaths = {
  repo_root: null,
  default_data_dir: "",
  data_dir: "",
  venv_python: null,
  uv: null,
  run_metrics: null,
  resource_manager: null,
  corpus_import: null,
  manifest: null,
  requirements_lock: null,
  env: {},
};

class MockBridge implements BackendBridge {
  readonly kind = "mock" as const;
  readonly paths: BackendPaths = MOCK_PATHS;

  available(): boolean {
    return false;
  }

  async request<T extends RpcMethod>(method: T): Promise<RpcMethods[T]["result"]> {
    console.warn("[bridge:mock] call to " + method + " is a no-op");
    if (method === "backend_paths") return MOCK_PATHS as RpcMethods[T]["result"];
    if (
      method === "scan_source_dir" ||
      method === "scan_source_tree" ||
      method === "list_csv_files"
    ) {
      return [] as RpcMethods[T]["result"];
    }
    if (method === "read_csv_preview") {
      return { headers: [], rows: [] } as RpcMethods[T]["result"];
    }
    if (method === "path_exists") return false as RpcMethods[T]["result"];
    if (method === "spawn_backend") return 0 as RpcMethods[T]["result"];
    return null as RpcMethods[T]["result"];
  }

  dispose(): void {}
}

let bridge: BackendBridge | null = null;
let listeningForLateBoot = false;

export const bridgeKind = writable<BridgeKind>(null);
export const bootRevision = writable(0);

export function currentBridge(): BackendBridge | null {
  return bridge;
}

async function performBoot(): Promise<BackendBridge> {
  const target = resolveBootTarget();

  if (target.kind === "mock") {
    bridge = new MockBridge();
    bridgeKind.set("mock");
    return bridge;
  }

  const wsUrl = target.kind === "desktop" ? target.boot.wsUrl : target.wsUrl;
  const token = target.kind === "desktop" ? target.boot.token : target.token;
  const carrier = new Carrier(wsUrl, token);
  try {
    await carrier.connect();
  } catch (err) {
    console.warn("[boot] carrier connect failed, using mock bridge:", err);
    bridge = new MockBridge();
    bridgeKind.set("mock");
    return bridge;
  }
  bridge = new RpcBridge(carrier, target.kind === "desktop" ? target.boot.paths : null);
  bridgeKind.set("rpc");
  return bridge;
}

let bootPromise: Promise<BackendBridge> | null = null;

/**
 * Boots the bridge exactly once: concurrent callers (main.ts and page
 * onMount handlers racing at startup) share the same promise, so only ONE
 * carrier connection is ever opened. Duplicate connections used to forward
 * every backend line twice into the console.
 */
export function bootBridge(): Promise<BackendBridge> {
  if (bridge) return Promise.resolve(bridge);
  if (!bootPromise) {
    bootPromise = performBoot().finally(() => {
      bootPromise = null;
    });
  }
  return bootPromise;
}

/** Forces a fresh boot (used when late boot info arrives in dev mode). */
export async function rebootBridge(): Promise<BackendBridge> {
  bridge?.dispose();
  bridge = null;
  return bootBridge();
}

/** Re-boot the bridge when the desktop shell injects boot info after page load. */
export function watchLateBoot(onReboot?: () => void): void {
  if (listeningForLateBoot || typeof window === "undefined") return;
  listeningForLateBoot = true;
  window.addEventListener(BOOT_EVENT, () => {
    void rebootBridge()
      .then(() => {
        bootRevision.update((value) => value + 1);
        onReboot?.();
      })
      .catch((err: unknown) => console.warn("[boot] late boot failed:", err));
  });
}
