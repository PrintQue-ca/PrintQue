import type { QueryClient } from '@tanstack/react-query'
import { io, type Socket } from 'socket.io-client'

/** Match api.ts: in dev, talk to Flask directly (avoids Vite WS proxy + Werkzeug issues). */
const SOCKET_URL = import.meta.env.DEV ? 'http://localhost:5000' : undefined

let socket: Socket | null = null

function isQueueMutationInFlight(queryClient: QueryClient): boolean {
  return (
    queryClient.isMutating({ mutationKey: ['reorderQueueJob'] }) > 0 ||
    queryClient.isMutating({ mutationKey: ['updateQueueQuantity'] }) > 0 ||
    queryClient.isMutating({ mutationKey: ['deleteQueueJob'] }) > 0 ||
    queryClient.isMutating({ mutationKey: ['bulkDeleteQueueJob'] }) > 0
  )
}

export function initSocket(queryClient: QueryClient) {
  if (socket) return socket

  socket = io(SOCKET_URL, {
    // Polling first: reliable with Flask threading + Werkzeug; upgrades when possible.
    transports: ['polling', 'websocket'],
    autoConnect: true,
  })

  socket.on('connect', () => {
    console.log('Socket connected:', socket?.id)
  })

  socket.on('disconnect', () => {
    console.log('Socket disconnected')
  })

  // Real-time status updates from the Flask backend
  socket.on('status_update', (data) => {
    if (data.printers) {
      queryClient.setQueryData(['printers'], data.printers)
    }
    if (data.orders) {
      if (!isQueueMutationInFlight(queryClient)) {
        queryClient.invalidateQueries({ queryKey: ['queue'] })
        queryClient.invalidateQueries({ queryKey: ['library'] })
      }
    }
    if (data.total_filament !== undefined) {
      queryClient.setQueryData(['stats', 'filament'], data.total_filament)
    }
  })

  // Printer-specific updates
  socket.on('printer_update', (data) => {
    queryClient.setQueryData(['printers'], (old: unknown) => {
      if (!Array.isArray(old)) return old
      return old.map((p) => {
        const printer = p as { name: string }
        return printer.name === data.name ? { ...printer, ...data } : printer
      })
    })
  })

  // Order updates
  socket.on('order_update', () => {
    // Skip refetch while reorder or debounced quantity save is in flight
    if (!isQueueMutationInFlight(queryClient)) {
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      queryClient.invalidateQueries({ queryKey: ['library'] })
    }
  })

  return socket
}

export function getSocket(): Socket | null {
  return socket
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect()
    socket = null
  }
}
