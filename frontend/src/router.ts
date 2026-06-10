// Minimal client-side router. The app has three fully separated surfaces, so
// the route is the single source of truth for which one renders.

export type Route =
  | { name: 'home' }
  | { name: 'public-claim'; eventId: string; claimId: string | null }
  | { name: 'staff'; eventId: string };

export function parseRoute(path: string): Route {
  const parts = path.replace(/^\/+|\/+$/g, '').split('/').filter(Boolean);
  // /e/{eventId}              -> public claim landing
  // /e/{eventId}/c/{claimId}  -> resume a specific claim
  // /e/{eventId}/staff        -> staff console
  if (parts[0] === 'e' && parts[1]) {
    const eventId = parts[1];
    if (parts[2] === 'staff') return { name: 'staff', eventId };
    if (parts[2] === 'c' && parts[3]) return { name: 'public-claim', eventId, claimId: parts[3] };
    return { name: 'public-claim', eventId, claimId: null };
  }
  return { name: 'home' };
}

/** Navigate without a full reload and notify listeners (popstate). */
export function navigate(path: string): void {
  if (path !== location.pathname) {
    history.pushState({}, '', path);
  }
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function claimPath(eventId: string, claimId: string): string {
  return `/e/${eventId}/c/${claimId}`;
}

export function eventPublicPath(eventId: string): string {
  return `/e/${eventId}`;
}

export function staffPath(eventId: string): string {
  return `/e/${eventId}/staff`;
}
