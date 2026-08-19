import { derived, get, writable } from "svelte/store";

import en from "./locales/en.json";
import zhCN from "./locales/zh-CN.json";

export type Locale = "zh-CN" | "en";

const dictionaries: Record<Locale, Record<string, string>> = {
  "zh-CN": zhCN,
  en,
};

const STORAGE_KEY = "syntactic-metrics-locale";

function detectInitialLocale(): Locale {
  // Only zh-CN and en are supported. The user's manual choice persists in
  // localStorage; otherwise the default is English regardless of the OS.
  if (typeof localStorage !== "undefined") {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "zh-CN" || saved === "en") return saved;
  }
  return "en";
}

export const locale = writable<Locale>(detectInitialLocale());

export function setLocale(next: Locale): void {
  locale.set(next);
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(STORAGE_KEY, next);
  }
  document.documentElement.lang = next;
  document.title = "SynSpectra";
}

function lookup(
  key: string,
  params?: Record<string, string | number>,
): string {
  const current = get(locale);
  const dict = dictionaries[current] ?? dictionaries.en;
  let text: string = dict[key] ?? key;
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

export const t = derived(locale, () => lookup);
