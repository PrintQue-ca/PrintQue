import type { Table } from '@tanstack/react-table'
import { useLayoutEffect, useRef } from 'react'

export const resizableTableDefaultColumn = {
  minSize: 56,
  size: 120,
  maxSize: 600,
  enableResizing: true,
} as const

/** Apply proportional column widths once so the table fills its container. */
export function useFitTableColumns<T>(
  table: Table<T>,
  containerRef: React.RefObject<HTMLElement | null>,
  weights: Record<string, number>
) {
  const fittedRef = useRef(false)

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el || fittedRef.current) return

    const fit = () => {
      const totalWidth = el.clientWidth
      if (totalWidth <= 0) return

      const columns = table.getAllLeafColumns().filter((col) => col.getCanResize())
      if (columns.length === 0) return

      const weightSum = columns.reduce((sum, col) => sum + (weights[col.id] ?? 1), 0)
      const sizing: Record<string, number> = {}

      for (const col of columns) {
        const weight = weights[col.id] ?? 1
        const min = col.columnDef.minSize ?? resizableTableDefaultColumn.minSize
        sizing[col.id] = Math.max(min, Math.floor((totalWidth * weight) / weightSum))
      }

      table.setColumnSizing(sizing)
      fittedRef.current = true
    }

    fit()
    const observer = new ResizeObserver(() => {
      if (!fittedRef.current) fit()
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [table, containerRef, weights])
}
