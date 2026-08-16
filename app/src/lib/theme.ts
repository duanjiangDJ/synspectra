import { get, writable } from "svelte/store";

import { bridgeKind, currentBridge } from "../bridge/bridge";
import { setWindowTheme } from "./backend";

export type Theme = "light" | "dark";

const THEME_KEY = "syntactic-metrics-theme";

function initialTheme(): Theme {
  if (typeof localStorage !== "undefined") {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  }
  if (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  ) {
    return "dark";
  }
  return "light";
}

export const theme = writable<Theme>(initialTheme());

export function setTheme(next: Theme): void {
  theme.set(next);
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(THEME_KEY, next);
  }
}

theme.subscribe((value) => {
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = value;
  }
});

// Keep the native window chrome (caption-button overlay colors) in sync.
export function applyThemeToWindow(next: Theme): void {
  if (currentBridge()?.kind === "rpc") {
    setWindowTheme(next).catch(() => {
      // Browser/mock mode has no window chrome to update.
    });
  }
}

theme.subscribe(applyThemeToWindow);

// The bridge boots asynchronously; when it becomes available, push the
// current theme so the caption buttons never start with the wrong colors.
bridgeKind.subscribe((kind) => {
  if (kind === "rpc") {
    applyThemeToWindow(get(theme));
  }
});
