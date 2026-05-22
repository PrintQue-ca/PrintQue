import { Link2, Unlink } from 'lucide-react'
import { useApiConnection } from '@/hooks/useApiConnection'

const TOOLTIP = {
  connected: 'Connected to API — live updates via Socket.IO',
  reconnecting: 'Reconnecting to API…',
  disconnected:
    'Disconnected from API — showing cached data, polling every few seconds for updates',
} as const

/** Subtle API connection indicator for the nav bar (icon + native hover tooltip). */
export function ConnectionBanner() {
  const state = useApiConnection()

  if (state === 'connected') {
    return (
      <output
        className="inline-flex text-green-600 dark:text-green-500"
        title={TOOLTIP.connected}
        aria-label={TOOLTIP.connected}
      >
        <Link2 className="h-4 w-4" aria-hidden />
      </output>
    )
  }

  if (state === 'reconnecting') {
    return (
      <output
        className="inline-flex text-amber-600 dark:text-amber-500"
        title={TOOLTIP.reconnecting}
        aria-label={TOOLTIP.reconnecting}
      >
        <Link2 className="h-4 w-4 animate-pulse opacity-70" aria-hidden />
      </output>
    )
  }

  return (
    <span
      className="inline-flex text-destructive"
      title={TOOLTIP.disconnected}
      role="alert"
      aria-label={TOOLTIP.disconnected}
    >
      <Unlink className="h-4 w-4" aria-hidden />
    </span>
  )
}
