import type { QueryClient } from '@tanstack/react-query'
import { io, type Socket } from 'socket.io-client'
import type { QueueJob } from '@/types'

/** Match api.ts: in dev, talk to Flask directly (avoids Vite WS proxy + Werkzeug issues). */
const SOCKET_URL = import.meta.env.DEV ? 'http://localhost:5000' : undefined

export type SocketConnectionState = 'connected' | 'disconnected' | 'reconnecting'

let socket: Socket | null = null
let connectionState: SocketConnectionState = 'disconnected'
const connectionListeners = new Set<() => void>()

function setConnectionState(next: SocketConnectionState) {
  if (connectionState === next) return
  connectionState = next
  for (const listener of connectionListeners) {
    listener()
  }
}

export function getSocketConnectionState(): SocketConnectionState {
  return connectionState
}

export function subscribeSocketConnection(listener: () => void): () => void {
  connectionListeners.add(listener)
  return () => {
    connectionListeners.delete(listener)
  }
}

function isQueueMutationInFlight(queryClient: QueryClient): boolean {
  return (
    queryClient.isMutating({ mutationKey: ['reorderQueueJob'] }) > 0 ||
    queryClient.isMutating({ mutationKey: ['updateQueueQuantity'] }) > 0 ||
    queryClient.isMutating({ mutationKey: ['updateQueuePaused'] }) > 0 ||
    queryClient.isMutating({ mutationKey: ['deleteQueueJob'] }) > 0 ||
    queryClient.isMutating({ mutationKey: ['bulkDeleteQueueJob'] }) > 0
  )
}

function applyQueueFromSocket(
  queryClient: QueryClient,
  data: { queue?: unknown; orders?: unknown }
) {
  if (isQueueMutationInFlight(queryClient)) return
  const raw = data.queue ?? data.orders
  if (!Array.isArray(raw)) {
    queryClient.invalidateQueries({ queryKey: ['queue'] })
    return
  }
  queryClient.setQueryData(['queue'], raw as QueueJob[])
}

export function initSocket(queryClient: QueryClient) {
  if (socket) return socket

  socket = io(SOCKET_URL, {
    transports: ['polling', 'websocket'],
    autoConnect: true,
    reconnection: true,
  })

  setConnectionState('reconnecting')

  socket.on('connect', () => {
    setConnectionState('connected')
    queryClient.invalidateQueries({ queryKey: ['printers'] })
    queryClient.invalidateQueries({ queryKey: ['queue'] })
  })

  socket.on('disconnect', () => {
    setConnectionState('disconnected')
  })

  socket.io.on('reconnect_attempt', () => {
    setConnectionState('reconnecting')
  })

  socket.on('connect_error', () => {
    setConnectionState('disconnected')
  })

  socket.on('status_update', (data) => {
    if (data.printers) {
      queryClient.setQueryData(['printers'], data.printers)
    }
    if (data.queue !== undefined || data.orders !== undefined) {
      applyQueueFromSocket(queryClient, data)
    }
    if (data.total_filament !== undefined) {
      queryClient.setQueryData(['stats', 'filament'], data.total_filament)
      queryClient.setQueryData(['stats'], (old: { total_filament?: number } | undefined) =>
        old ? { ...old, total_filament: data.total_filament } : old
      )
    }
  })

  socket.on('printer_update', (data) => {
    queryClient.setQueryData(['printers'], (old: unknown) => {
      if (!Array.isArray(old)) return old
      return old.map((p) => {
        const printer = p as { name: string }
        return printer.name === data.name ? { ...printer, ...data } : printer
      })
    })
  })

  socket.on('order_update', (data: { queue?: unknown; orders?: unknown } | undefined) => {
    if (data?.queue !== undefined || data?.orders !== undefined) {
      applyQueueFromSocket(queryClient, data)
    } else if (!isQueueMutationInFlight(queryClient)) {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    }
  })

  if (socket.connected) {
    setConnectionState('connected')
  }

  return socket
}

export function getSocket(): Socket | null {
  return socket
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect()
    socket = null
    setConnectionState('disconnected')
  }
}
