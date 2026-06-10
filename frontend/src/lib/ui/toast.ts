// App-wide toast queue. Success/info toasts confirm an action briefly (and
// pause while hovered); error toasts stay until dismissed — they are often
// the only record that an action failed.

import { writable } from 'svelte/store';

export type ToastKind = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const store = writable<Toast[]>([]);
const timers = new Map<number, ReturnType<typeof setTimeout>>();
let nextId = 1;

const TTL = 4000;

function dismiss(id: number): void {
  const t = timers.get(id);
  if (t) clearTimeout(t);
  timers.delete(id);
  store.update((list) => list.filter((x) => x.id !== id));
}

/** Pause auto-dismissal (e.g. while hovered/focused). */
function hold(id: number): void {
  const t = timers.get(id);
  if (t) clearTimeout(t);
  timers.delete(id);
}

/** Resume auto-dismissal after a hold. Errors never auto-dismiss. */
function release(id: number, kind: ToastKind): void {
  if (kind === 'error') return;
  hold(id);
  timers.set(id, setTimeout(() => dismiss(id), TTL));
}

function push(kind: ToastKind, message: string): void {
  const id = nextId++;
  store.update((list) => [...list.slice(-3), { id, kind, message }]);
  if (kind !== 'error') timers.set(id, setTimeout(() => dismiss(id), TTL));
}

export const toasts = {
  subscribe: store.subscribe,
  success: (message: string) => push('success', message),
  error: (message: string) => push('error', message),
  info: (message: string) => push('info', message),
  dismiss,
  hold,
  release,
};
