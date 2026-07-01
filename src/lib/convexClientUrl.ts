/** Resolve Convex URL for the current browser (normalize localhost vs 127.0.0.1). */
export function resolveConvexClientUrl(envUrl: string): string {
  const trimmed = envUrl.trim()
  if (!trimmed || typeof window === 'undefined') return trimmed

  try {
    const parsed = new URL(trimmed)
    const pageHost = window.location.hostname
    const pageLoopback = pageHost === 'localhost' || pageHost === '127.0.0.1'
    const convexLoopback =
      parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1'
    if (pageLoopback && convexLoopback && parsed.hostname !== pageHost) {
      parsed.hostname = pageHost
      return parsed.toString().replace(/\/$/, '')
    }
  } catch {
    /* ignore malformed URL */
  }

  return trimmed
}
