/**
 * Tests for PrinterCard component.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PrinterCard } from '../../components/printers/PrinterCard'
import type { Printer } from '../../types'

// Mock the hooks
vi.mock('../../hooks', () => ({
  useStopPrint: () => ({ mutate: vi.fn(), isPending: false }),
  usePausePrint: () => ({ mutate: vi.fn(), isPending: false }),
  useResumePrint: () => ({ mutate: vi.fn(), isPending: false }),
  useMarkReady: () => ({ mutate: vi.fn(), isPending: false }),
  useClearError: () => ({ mutate: vi.fn(), isPending: false }),
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

const basePrinter: Printer = {
  name: 'Test Printer',
  ip: '192.168.1.100',
  type: 'prusa',
  status: 'READY',
}

describe('PrinterCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('should render printer name and IP', () => {
      render(<PrinterCard printer={basePrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('Test Printer')).toBeInTheDocument()
      expect(screen.getByText('192.168.1.100')).toBeInTheDocument()
    })

    it('should render printer type badge', () => {
      render(<PrinterCard printer={basePrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('prusa')).toBeInTheDocument()
    })

    it('should render status badge', () => {
      render(<PrinterCard printer={basePrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('Ready')).toBeInTheDocument()
    })
  })

  describe('Ready State', () => {
    it('should show ready message when printer is READY', () => {
      render(<PrinterCard printer={basePrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('Ready for printing')).toBeInTheDocument()
    })
  })

  describe('Printing State', () => {
    const printingPrinter: Printer = {
      ...basePrinter,
      status: 'PRINTING',
      progress: 45,
      current_file: 'test_part.gcode',
      time_remaining: 3600,
    }

    it('should show progress when printing', () => {
      render(<PrinterCard printer={printingPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('45%')).toBeInTheDocument()
      expect(screen.getByText('test_part.gcode')).toBeInTheDocument()
    })

    it('should show time remaining', () => {
      render(<PrinterCard printer={printingPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('~60m remaining')).toBeInTheDocument()
    })

    it('should show Pause and Stop buttons when printing', () => {
      render(<PrinterCard printer={printingPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
    })
  })

  describe('Paused State', () => {
    const pausedPrinter: Printer = {
      ...basePrinter,
      status: 'PAUSED',
      progress: 50,
      current_file: 'paused_part.gcode',
    }

    it('should show Resume and Stop buttons when paused', () => {
      render(<PrinterCard printer={pausedPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
    })
  })

  describe('Finished State', () => {
    const finishedPrinter: Printer = {
      ...basePrinter,
      status: 'FINISHED',
      current_file: 'completed_part.gcode',
    }

    it('should show Mark Ready button when finished', () => {
      render(<PrinterCard printer={finishedPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByRole('button', { name: /mark ready/i })).toBeInTheDocument()
    })

    it('should show completed file name', () => {
      render(<PrinterCard printer={finishedPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText(/completed_part.gcode/)).toBeInTheDocument()
    })
  })

  describe('Error State', () => {
    const errorPrinter: Printer = {
      ...basePrinter,
      status: 'ERROR',
      error_message: 'Filament runout detected',
    }

    it('should show error message', () => {
      render(<PrinterCard printer={errorPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('Printer Error')).toBeInTheDocument()
      expect(screen.getByText('Filament runout detected')).toBeInTheDocument()
    })

    it('should show Clear Error button', () => {
      render(<PrinterCard printer={errorPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByRole('button', { name: /clear error/i })).toBeInTheDocument()
    })

    it('should show HMS alerts for Bambu printers', () => {
      const bambuError: Printer = {
        ...errorPrinter,
        type: 'bambu',
        hms_alerts: ['Nozzle clogged', 'Temperature warning'],
      }

      render(<PrinterCard printer={bambuError} />, { wrapper: createWrapper() })

      expect(screen.getByText('HMS Alerts:')).toBeInTheDocument()
      expect(screen.getByText('Nozzle clogged')).toBeInTheDocument()
      expect(screen.getByText('Temperature warning')).toBeInTheDocument()
    })
  })

  describe('Cooling State', () => {
    const coolingPrinter: Printer = {
      ...basePrinter,
      status: 'COOLING',
      bed_temp: 45.5,
    }

    it('should show cooling message', () => {
      render(<PrinterCard printer={coolingPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByText('Cooling Down')).toBeInTheDocument()
      expect(screen.getByText(/Waiting for bed to cool/)).toBeInTheDocument()
    })

    it('should show Skip Cooldown button', () => {
      render(<PrinterCard printer={coolingPrinter} />, { wrapper: createWrapper() })

      expect(screen.getByRole('button', { name: /skip cooldown/i })).toBeInTheDocument()
    })
  })

  describe('Temperature Display', () => {
    it('should show temperatures for online printers', () => {
      const printerWithTemps: Printer = {
        ...basePrinter,
        nozzle_temp: 210.5,
        bed_temp: 60.2,
      }

      render(<PrinterCard printer={printerWithTemps} />, { wrapper: createWrapper() })

      expect(screen.getByText(/Nozzle: 210.5°C/)).toBeInTheDocument()
      expect(screen.getByText(/Bed: 60.2°C/)).toBeInTheDocument()
    })

    it('should not show temperatures for offline printers', () => {
      const offlinePrinter: Printer = {
        ...basePrinter,
        status: 'OFFLINE',
        nozzle_temp: 0,
        bed_temp: 0,
      }

      render(<PrinterCard printer={offlinePrinter} />, { wrapper: createWrapper() })

      expect(screen.queryByText(/Nozzle:/)).not.toBeInTheDocument()
    })
  })
})
