/** REST polling when Socket.IO is disconnected (fallback). */
export const DISCONNECTED_REFETCH_MS = 8_000

/** Rare safety-net poll when connected (optional; false disables). */
export const CONNECTED_REFETCH_MS = false as const

export function adaptiveRefetchInterval(isConnected: boolean): number | false {
  return isConnected ? CONNECTED_REFETCH_MS : DISCONNECTED_REFETCH_MS
}

/** Library changes rarely — only poll on disconnect if cache is very stale. */
export const LIBRARY_DISCONNECTED_STALE_MS = 5 * 60 * 1000

export function libraryRefetchInterval(
  isConnected: boolean,
  dataUpdatedAt: number | undefined
): number | false {
  if (isConnected) return false
  if (dataUpdatedAt === undefined) return DISCONNECTED_REFETCH_MS
  const age = Date.now() - dataUpdatedAt
  return age >= LIBRARY_DISCONNECTED_STALE_MS ? DISCONNECTED_REFETCH_MS : false
}
