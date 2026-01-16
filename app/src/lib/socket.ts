import { io, Socket } from 'socket.io-client'
import type { QueryClient } from '@tanstack/react-query'

let socket: Socket | null = null

export function initSocket(queryClient: QueryClient) {
  if (socket) return socket

  socket = io({
    transports: ['websocket'],
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
      // Use invalidateQueries instead of setQueryData to avoid overwriting
      // local state with potentially stale socket data (e.g., after deletions)
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    }
    if (data.total_filament !== undefined) {
      queryClient.setQueryData(['stats', 'filament'], data.total_filament)
    }
  })

  // Printer-specific updates
  socket.on('printer_update', (data) => {
    queryClient.setQueryData(['printers'], (old: unknown[] | undefined) => {
      if (!old) return old
      return old.map((p: { name: string }) =>
        p.name === data.name ? { ...p, ...data } : p
      )
    })
  })

  // Order updates
  socket.on('order_update', (data) => {
    queryClient.invalidateQueries({ queryKey: ['orders'] })
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
