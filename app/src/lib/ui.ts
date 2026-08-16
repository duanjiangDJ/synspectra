import { get, writable } from "svelte/store";

export interface Toast {
  id: number;
  type: "info" | "success" | "warning" | "error";
  message: string;
  createdAt: number;
}

export interface ConfirmRequest {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  input?: { label: string; value: string };
}

export const toasts = writable<Toast[]>([]);
export const confirmState = writable<{
  request: ConfirmRequest | null;
  onAnswer: ((value: boolean | string | null) => void) | null;
}>({ request: null, onAnswer: null });

let toastId = 0;

export function addToast(
  type: Toast["type"],
  message: string,
  timeout = 4500,
): void {
  // Dedupe: the same message coming from multiple event paths (stdout +
  // stderr, task-end + error) must not stack duplicate notifications.
  const now = Date.now();
  let id = 0;
  toasts.update((items) => {
    if (
      items.some(
        (item) => item.message === message && now - item.createdAt < 3000,
      )
    ) {
      return items;
    }
    id = ++toastId;
    return [...items.slice(-4), { id, type, message, createdAt: now }];
  });
  if (!id) return;
  window.setTimeout(() => removeToast(id), timeout);
}

export function removeToast(id: number): void {
  toasts.update((items) => items.filter((item) => item.id !== id));
}

export function askConfirm(request: ConfirmRequest): Promise<boolean> {
  return new Promise((resolve) => {
    confirmState.set({
      request,
      onAnswer: (value) => resolve(value === true),
    });
  });
}

export function askInput(request: ConfirmRequest): Promise<string | null> {
  return new Promise((resolve) => {
    confirmState.set({
      request,
      onAnswer: (value) =>
        resolve(typeof value === "string" && value.trim() ? value : null),
    });
  });
}

export function answerConfirm(value: boolean | string | null): void {
  const current = get(confirmState);
  current.onAnswer?.(value);
  confirmState.set({ request: null, onAnswer: null });
}
