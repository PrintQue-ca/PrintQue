import { describe, expect, it } from 'vitest'
import {
  findQueueJobForPrinter,
  formatQueueJobProgressSummary,
  getCurrentCopyLabel,
  getPrinterQueueJobId,
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

describe('formatQueueJobProgressSummary', () => {
  it('formats progress string', () => {
    expect(formatQueueJobProgressSummary(sampleJob)).toBe('3 / 10 started · 7 remaining')
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
