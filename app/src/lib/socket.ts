import type { QueryClient } from '@tanstack/react-query'
import { io, type Socket } from 'socket.io-client'

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
      // Only update if no mutation is in progress to avoid flickering during drag-drop
      const isMutating = queryClient.isMutating({ mutationKey: ['reorderOrder'] })
      if (!isMutating) {
        queryClient.invalidateQueries({ queryKey: ['orders'] })
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
    // Only update if no mutation is in progress to avoid flickering during drag-drop
    const isMutating = queryClient.isMutating({ mutationKey: ['reorderOrder'] })
    if (!isMutating) {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
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
