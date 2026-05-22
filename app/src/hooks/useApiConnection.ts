import { useSyncExternalStore } from 'react'
import { adaptiveRefetchInterval } from '@/lib/refetch-intervals'
import {
  getSocketConnectionState,
  type SocketConnectionState,
  subscribeSocketConnection,
} from '@/lib/socket'

export function useApiConnection(): SocketConnectionState {
  return useSyncExternalStore(
    subscribeSocketConnection,
    getSocketConnectionState,
    () => 'disconnected' as SocketConnectionState
  )
}

export function useIsApiConnected(): boolean {
  return useApiConnection() === 'connected'
}

/** TanStack Query refetchInterval: off when socket connected, faster when disconnected. */
export function useAdaptiveRefetchInterval(): number | false {
  const connected = useIsApiConnected()
  return adaptiveRefetchInterval(connected)
}
