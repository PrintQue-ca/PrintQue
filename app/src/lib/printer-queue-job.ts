import type { Printer, PrinterStatus, QueueJob } from '@/types'

export const ACTIVE_JOB_PRINTER_STATUSES: PrinterStatus[] = [
  'PRINTING',
  'PAUSED',
  'PREPARING',
  'FINISHED',
  'COOLING',
  'EJECTING',
]

export function getPrinterQueueJobId(printer: Printer): number | null {
  const raw = printer.queue_job_id ?? printer.order_id ?? printer.cooldown_order_id
  if (raw == null) return null
  const id = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(id) ? id : null
}

export function isActiveJobPrinterStatus(status: PrinterStatus): boolean {
  return ACTIVE_JOB_PRINTER_STATUSES.includes(status)
}

export function findQueueJobForPrinter(printer: Printer, jobs: QueueJob[]): QueueJob | null {
  const jobId = getPrinterQueueJobId(printer)
  if (jobId == null) return null
  return jobs.find((job) => job.id === jobId) ?? null
}

export function getQueueJobDisplayName(job: QueueJob): string {
  const name = job.name?.trim()
  return name || job.filename
}

export function getQueueJobProgress(job: QueueJob) {
  const total = job.quantity
  const started = job.sent
  const remaining = Math.max(0, total - started)
  return { total, started, remaining }
}

export function formatQueueJobProgressSummary(job: QueueJob): string {
  const { started, total, remaining } = getQueueJobProgress(job)
  return `${started} / ${total} started · ${remaining} remaining`
}

export function getCurrentCopyLabel(job: QueueJob, printerStatus: PrinterStatus): string | null {
  if (!['PRINTING', 'PAUSED', 'PREPARING'].includes(printerStatus)) {
    return null
  }
  const { total, started } = getQueueJobProgress(job)
  if (total <= 0) return null
  const copy = Math.min(Math.max(started, 1), total)
  return `Currently printing copy ${copy} of ${total}`
}
