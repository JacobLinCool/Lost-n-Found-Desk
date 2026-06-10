function statusMessage(status: number, detail?: string): string {
  if (detail) return detail;
  if (status === 413) return 'That file is too large — try a smaller photo.';
  if (status === 401) return "That password doesn't match. Check it and try again.";
  if (status === 404) return "We couldn't find that. The link or code may be wrong.";
  if (status >= 500) return 'Something went wrong on our side. Please try again in a moment.';
  return `The request didn't go through (error ${status}).`;
}

/** Error carrying the HTTP status, so callers can react to 401/404 precisely
 * instead of guessing from the message (status is 0 for network failures). */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, options);
  } catch (_) {
    // fetch rejects (network down, DNS, dropped wifi) before any HTTP response.
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  const data = (await res.json().catch(() => ({}))) as T & { detail?: string };
  if (!res.ok) throw new ApiError(statusMessage(res.status, data?.detail), res.status);
  return data as T;
}

export function staffHeaders(
  password: string,
  extra: Record<string, string> = {},
): Record<string, string> {
  return { 'x-staff-password': password, ...extra };
}

/** Fetch a staff-only image as an object URL using the staff password header. */
export async function authorizedImageSrc(path: string, password: string): Promise<string> {
  const res = await fetch(path, { headers: staffHeaders(password) });
  if (!res.ok) throw new Error(`The photo couldn't be loaded (error ${res.status}).`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/** Absolute URL for a path, for share links / QR codes. */
export function absoluteUrl(path: string): string {
  return `${window.location.origin}${path}`;
}
