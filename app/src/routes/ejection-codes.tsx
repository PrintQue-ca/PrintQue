import { createFileRoute } from '@tanstack/react-router'
import { EjectionCodesManager } from '@/components/orders/EjectionCodesManager'

export const Route = createFileRoute('/ejection-codes')({
  component: EjectionCodesPage,
})

function EjectionCodesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Ejection Codes</h1>
        <p className="text-muted-foreground">
          Manage G-code presets for auto-ejection after prints
        </p>
      </div>
      <EjectionCodesManager />
    </div>
  )
}
