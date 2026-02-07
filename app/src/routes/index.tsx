import { createFileRoute, Link } from '@tanstack/react-router'
import { Loader2, Plus } from 'lucide-react'
import { StatsCards } from '@/components/layout/StatsCards'
import { NewOrderForm } from '@/components/orders/NewOrderForm'
import { OrdersTable } from '@/components/orders/OrdersTable'
import { PrinterCard } from '@/components/printers/PrinterCard'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useOrders, usePrinters } from '@/hooks'

export const Route = createFileRoute('/')({ component: Dashboard })

function Dashboard() {
  const { data: printers, isLoading: printersLoading } = usePrinters()
  const { data: orders, isLoading: ordersLoading } = useOrders()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Monitor and manage your print library</p>
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
                <div className="flex flex-col items-center justify-center gap-4 py-8 text-muted-foreground">
                  <p>No printers configured.</p>
                  <p className="text-sm">Add a printer to get started.</p>
                  <Button asChild>
                    <Link to="/printers">
                      <Plus className="h-4 w-4" />
                      Add printer
                    </Link>
                  </Button>
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
        </div>
      </div>
    </div>
  )
}
