import { ChevronRight } from 'lucide-react'
import {
  formatQueueJobProgressSummary,
  getPrinterQueueJobId,
  getQueueJobDisplayName,
} from '@/lib/printer-queue-job'
import { cn } from '@/lib/utils'
import type { Printer, QueueJob } from '@/types'

interface PrinterActiveJobButtonProps {
  printer: Printer
  job: QueueJob | null
  printers?: Printer[]
  onClick: () => void
  className?: string
}

export function PrinterActiveJobButton({
  printer,
  job,
  printers = [],
  onClick,
  className,
}: PrinterActiveJobButtonProps) {
  const currentFileName =
    typeof printer.current_file === 'string' ? printer.current_file : 'Unknown file'
  const hasJobId = getPrinterQueueJobId(printer) != null

  if (!hasJobId) {
    return null
  }

  const title = job ? getQueueJobDisplayName(job) : 'Unknown queue job'
  const subtitle = job ? formatQueueJobProgressSummary(job, printers) : currentFileName

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full rounded-lg border bg-muted/40 px-3 py-2 text-left transition-colors',
        'hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{title}</p>
          <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
      </div>
    </button>
  )
}
