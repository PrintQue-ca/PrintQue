import { describe, expect, it } from 'vitest'
import {
  countPrintersInProgressForJob,
  findQueueJobForPrinter,
  formatQueueJobProgressSummary,
  getCurrentCopyLabel,
  getPrinterQueueJobId,
  getQueueJobActivity,
  getQueueJobProgress,
  isActiveJobPrinterStatus,
} from '../../lib/printer-queue-job'
import type { Printer, QueueJob } from '../../types'

const sampleJob: QueueJob = {
  id: 5,
  filename: 'part.gcode',
  name: 'Widget',
  quantity: 10,
  sent: 3,
  status: 'partial',
  groups: ['Default'],
}

const samplePrinter: Printer = {
  name: 'P1',
  ip: '192.168.1.1',
  type: 'bambu',
  status: 'PRINTING',
  order_id: 5,
}

describe('getPrinterQueueJobId', () => {
  it('prefers queue_job_id', () => {
    expect(getPrinterQueueJobId({ ...samplePrinter, queue_job_id: 9, order_id: 5 })).toBe(9)
  })

  it('falls back to order_id then cooldown_order_id', () => {
    expect(getPrinterQueueJobId({ ...samplePrinter, order_id: 5 })).toBe(5)
    expect(
      getPrinterQueueJobId({
        ...samplePrinter,
        order_id: null,
        cooldown_order_id: 7,
      })
    ).toBe(7)
  })

  it('returns null when no id', () => {
    expect(
      getPrinterQueueJobId({ ...samplePrinter, order_id: null, cooldown_order_id: null })
    ).toBe(null)
  })
})

describe('findQueueJobForPrinter', () => {
  it('finds job by id', () => {
    expect(findQueueJobForPrinter(samplePrinter, [sampleJob])).toEqual(sampleJob)
  })

  it('returns null when job missing', () => {
    expect(findQueueJobForPrinter(samplePrinter, [])).toBeNull()
  })
})

describe('getQueueJobProgress', () => {
  it('computes total started remaining', () => {
    expect(getQueueJobProgress(sampleJob)).toEqual({
      total: 10,
      started: 3,
      remaining: 7,
    })
  })
})

describe('getQueueJobActivity', () => {
  it('treats all sent as completed when no active printers', () => {
    expect(getQueueJobActivity(sampleJob, [])).toEqual({
      total: 10,
      sent: 3,
      inProgress: 0,
      completed: 3,
      pending: 7,
    })
  })

  it('subtracts active printers from completed', () => {
    const printers: Printer[] = [
      { ...samplePrinter, name: 'P1', order_id: 5, status: 'PRINTING' },
      { ...samplePrinter, name: 'P2', order_id: 5, status: 'COOLING' },
    ]
    expect(getQueueJobActivity({ ...sampleJob, sent: 5 }, printers)).toEqual({
      total: 10,
      sent: 5,
      inProgress: 2,
      completed: 3,
      pending: 5,
    })
  })

  it('clamps completed when inProgress exceeds sent', () => {
    const printers: Printer[] = [
      { ...samplePrinter, name: 'P1', order_id: 5, status: 'PRINTING' },
      { ...samplePrinter, name: 'P2', order_id: 5, status: 'PRINTING' },
      { ...samplePrinter, name: 'P3', order_id: 5, status: 'EJECTING' },
    ]
    expect(getQueueJobActivity({ ...sampleJob, sent: 2 }, printers).completed).toBe(0)
  })
})

describe('countPrintersInProgressForJob', () => {
  it('ignores ready printers and other jobs', () => {
    const printers: Printer[] = [
      { ...samplePrinter, name: 'P1', order_id: 5, status: 'PRINTING' },
      { ...samplePrinter, name: 'P2', order_id: 5, status: 'READY' },
      { ...samplePrinter, name: 'P3', order_id: 99, status: 'PRINTING' },
    ]
    expect(countPrintersInProgressForJob(5, printers)).toBe(1)
  })
})

describe('formatQueueJobProgressSummary', () => {
  it('formats activity string', () => {
    expect(formatQueueJobProgressSummary(sampleJob)).toBe(
      '3 completed · 0 in progress · 7 pending (10 total)'
    )
  })
})

describe('isActiveJobPrinterStatus', () => {
  it('includes workflow states', () => {
    expect(isActiveJobPrinterStatus('PRINTING')).toBe(true)
    expect(isActiveJobPrinterStatus('COOLING')).toBe(true)
    expect(isActiveJobPrinterStatus('READY')).toBe(false)
  })
})

describe('getCurrentCopyLabel', () => {
  it('returns label when plate active', () => {
    expect(getCurrentCopyLabel(sampleJob, 'PRINTING')).toBe('Currently printing copy 3 of 10')
  })

  it('returns null when not printing', () => {
    expect(getCurrentCopyLabel(sampleJob, 'FINISHED')).toBeNull()
  })
})
