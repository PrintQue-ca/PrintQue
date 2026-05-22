import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  formatQueueJobProgressSummary,
  getCurrentCopyLabel,
  getQueueJobDisplayName,
  getQueueJobProgress,
} from '@/lib/printer-queue-job'
import type { Printer, QueueJob, QueueJobStatus } from '@/types'

interface QueueJobDetailSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  printer: Printer
  job: QueueJob | null
}

const queueStatusLabels: Record<QueueJobStatus, string> = {
  pending: 'Pending',
  partial: 'In progress',
  fulfilled: 'Fulfilled',
}

const queueStatusColors: Record<QueueJobStatus, string> = {
  pending: 'bg-gray-500',
  partial: 'bg-blue-500',
  fulfilled: 'bg-green-500',
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className="text-right font-medium break-all">{value}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="space-y-2 rounded-lg border p-3">{children}</div>
    </section>
  )
}

export function QueueJobDetailSheet({
  open,
  onOpenChange,
  printer,
  job,
}: QueueJobDetailSheetProps) {
  const currentFileName =
    typeof printer.current_file === 'string' ? printer.current_file : 'Unknown file'
  const jobName = job ? getQueueJobDisplayName(job) : 'Unknown queue job'
  const progress = job ? getQueueJobProgress(job) : null
  const copyLabel = job ? getCurrentCopyLabel(job, printer.status) : null
  const groupsLabel = job?.groups?.length ? job.groups.map((g) => String(g)).join(', ') : '—'

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{jobName}</SheetTitle>
          <SheetDescription>
            Queue job on {printer.name}
            {job ? ` · #${job.id}` : ''}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-6 px-4 pb-6">
          <Section title="Job">
            {job ? (
              <>
                <DetailRow label="Filename" value={job.filename} />
                <DetailRow
                  label="Status"
                  value={
                    <Badge className={queueStatusColors[job.status]}>
                      {queueStatusLabels[job.status]}
                    </Badge>
                  }
                />
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  This printer references a queue job that could not be found. It may have been
                  removed.
                </p>
                <DetailRow label="File on printer" value={currentFileName} />
              </>
            )}
          </Section>

          {job && progress && (
            <Section title="Order progress">
              <DetailRow label="Total" value={progress.total} />
              <DetailRow label="Started" value={progress.started} />
              <DetailRow label="Remaining" value={progress.remaining} />
              <DetailRow label="Summary" value={formatQueueJobProgressSummary(job)} />
              {copyLabel && <p className="text-sm text-muted-foreground">{copyLabel}</p>}
            </Section>
          )}

          <Section title="This printer">
            <DetailRow label="Printer" value={printer.name} />
            <DetailRow label="Status" value={printer.status} />
            {(printer.status === 'PRINTING' ||
              printer.status === 'PAUSED' ||
              printer.status === 'PREPARING') && (
              <>
                <DetailRow
                  label="Plate progress"
                  value={printer.progress !== undefined ? `${printer.progress}%` : '—'}
                />
                {printer.time_remaining !== undefined && (
                  <DetailRow
                    label="Time remaining"
                    value={`~${Math.floor(printer.time_remaining / 60)} min`}
                  />
                )}
              </>
            )}
            <DetailRow label="Current file" value={currentFileName} />
          </Section>

          {job && (
            <Section title="Settings">
              <DetailRow label="Groups" value={groupsLabel} />
              <DetailRow
                label="Ejection"
                value={
                  job.ejection_enabled
                    ? job.ejection_code_name || job.ejection_code_id || 'Enabled'
                    : 'Off'
                }
              />
              {job.cooldown_temp != null && (
                <DetailRow label="Cooldown target" value={`${job.cooldown_temp}°C`} />
              )}
            </Section>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
