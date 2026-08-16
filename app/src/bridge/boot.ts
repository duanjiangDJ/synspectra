import type { BootInfo } from "./contracts";

declare global {
  interface Window {
    __SYNM_BOOT__?: BootInfo;
  }
}

/** Dispatched by the desktop shell when boot info arrives after page load (dev mode). */
export const BOOT_EVENT = "synm:boot";

export function readBoot(): BootInfo | null {
  if (typeof window === "undefined") return null;
  return window.__SYNM_BOOT__ ?? null;
}

export type BootTarget =
  | { kind: "desktop"; boot: BootInfo }
  | { kind: "browser"; wsUrl: string; token: string }
  | { kind: "mock" };

export function resolveBootTarget(): BootTarget {
  const boot = readBoot();
  if (boot?.wsUrl) {
    return { kind: "desktop", boot };
  }
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const wsUrl = params.get("ws");
    if (wsUrl) {
      return { kind: "browser", wsUrl, token: params.get("token") ?? "dev" };
    }
    if (import.meta.env.DEV) {
      // Browser dev mode without an explicit carrier: fall back to the
      // default headless carrier port. Failure falls back to the mock bridge.
      return { kind: "browser", wsUrl: "ws://127.0.0.1:8787/carrier", token: "dev" };
    }
  }
  return { kind: "mock" };
}
