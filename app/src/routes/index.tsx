import { createFileRoute } from '@tanstack/react-router'
import { usePrinters, useOrders } from '@/hooks'
import { StatsCards } from '@/components/layout/StatsCards'
import { PrinterCard } from '@/components/printers/PrinterCard'
import { OrdersTable } from '@/components/orders/OrdersTable'
import { NewOrderForm } from '@/components/orders/NewOrderForm'
import { EjectionCodesManager } from '@/components/orders/EjectionCodesManager'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2 } from 'lucide-react'

export const Route = createFileRoute('/')({ component: Dashboard })

function Dashboard() {
  const { data: printers, isLoading: printersLoading } = usePrinters()
  const { data: orders, isLoading: ordersLoading } = useOrders()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Monitor and manage your print library
        </p>
      </div>

      {/* Stats Overview */}
      <StatsCards />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Printers Grid - 2 columns on large screens */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Printers</CardTitle>
            </CardHeader>
            <CardContent>
              {printersLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : printers && printers.length > 0 ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {printers.map((printer) => (
                    <PrinterCard key={printer.name} printer={printer} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <p>No printers configured.</p>
                  <p className="text-sm">Go to the Printers page to add one.</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Orders Table */}
          <Card>
            <CardHeader>
              <CardTitle>Library</CardTitle>
            </CardHeader>
            <CardContent>
              {ordersLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <OrdersTable orders={orders || []} />
              )}
            </CardContent>
          </Card>
        </div>

        {/* New Order Form - Sidebar */}
        <div className="space-y-4">
          <NewOrderForm />
          <EjectionCodesManager />
        </div>
      </div>
    </div>
  )
}
