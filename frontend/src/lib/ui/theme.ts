// Theme preference: 'light' | 'dark' | 'system', persisted per device.
// index.html applies the stored preference before first paint (no flash);
// this module owns it from then on and tracks OS changes while on 'system'.

import { writable } from 'svelte/store';

export type ThemePref = 'light' | 'dark' | 'system';

const KEY = 'lfd_theme';
const media = window.matchMedia('(prefers-color-scheme: dark)');

function storedPref(): ThemePref {
  const v = localStorage.getItem(KEY);
  return v === 'light' || v === 'dark' ? v : 'system';
}

function apply(pref: ThemePref): void {
  const dark = pref === 'dark' || (pref === 'system' && media.matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

export const themePref = writable<ThemePref>(storedPref());

themePref.subscribe((pref) => {
  if (pref === 'system') localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, pref);
  apply(pref);
});

media.addEventListener('change', () => apply(storedPref()));

/** Cycle system → light → dark → system. */
export function cycleTheme(): void {
  themePref.update((p) => (p === 'system' ? 'light' : p === 'light' ? 'dark' : 'system'));
}
