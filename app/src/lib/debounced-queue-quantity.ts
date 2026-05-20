import type { QueryClient } from '@tanstack/react-query'
import type { QueueJob } from '@/types'

export const QUANTITY_DEBOUNCE_MS = 400

type DebounceState = {
  timers: Map<number, ReturnType<typeof setTimeout>>
  pending: Map<number, number>
}

const stateByClient = new WeakMap<QueryClient, DebounceState>()

function getState(queryClient: QueryClient): DebounceState {
  let state = stateByClient.get(queryClient)
  if (!state) {
    state = { timers: new Map(), pending: new Map() }
    stateByClient.set(queryClient, state)
  }
  return state
}

function getJob(queryClient: QueryClient, id: number): QueueJob | undefined {
  const queue = queryClient.getQueryData<QueueJob[]>(['queue'])
  return queue?.find((j) => j.id === id)
}

function clampQuantity(queryClient: QueryClient, id: number, quantity: number): number {
  const sent = getJob(queryClient, id)?.sent ?? 0
  return Math.max(quantity, sent)
}

export type QueueQuantityPatch = (vars: { id: number; quantity: number }) => void

export function createDebouncedQueueQuantityActions(
  queryClient: QueryClient,
  patch: QueueQuantityPatch
) {
  const { timers, pending } = getState(queryClient)

  const applyOptimistic = (id: number, quantity: number) => {
    queryClient.setQueryData<QueueJob[]>(['queue'], (old) => {
      if (!old) return old
      return old.map((job) => (job.id === id ? { ...job, quantity } : job))
    })
    pending.set(id, quantity)
  }

  const saveQuantity = (id: number, quantity: number) => {
    const clamped = clampQuantity(queryClient, id, quantity)
    pending.delete(id)
    patch({ id, quantity: clamped })
  }

  const scheduleSave = (id: number) => {
    const existing = timers.get(id)
    if (existing) clearTimeout(existing)
    const timer = setTimeout(() => {
      timers.delete(id)
      const qty = pending.get(id)
      if (qty !== undefined) {
        saveQuantity(id, qty)
      }
    }, QUANTITY_DEBOUNCE_MS)
    timers.set(id, timer)
  }

  const bumpQuantity = (id: number, delta: number) => {
    const job = getJob(queryClient, id)
    if (!job) return
    const current = pending.get(id) ?? job.quantity
    const next = clampQuantity(queryClient, id, current + delta)
    if (next === current) return
    applyOptimistic(id, next)
    scheduleSave(id)
  }

  const setQuantity = (id: number, quantity: number) => {
    const job = getJob(queryClient, id)
    if (!job) return
    const next = clampQuantity(queryClient, id, quantity)
    const current = pending.get(id) ?? job.quantity
    if (next === current) return
    applyOptimistic(id, next)
    scheduleSave(id)
  }

  const flushQuantity = (id: number) => {
    const existing = timers.get(id)
    if (existing) {
      clearTimeout(existing)
      timers.delete(id)
    }
    const qty = pending.get(id)
    if (qty !== undefined) {
      saveQuantity(id, qty)
    }
  }

  return { bumpQuantity, setQuantity, flushQuantity }
}
