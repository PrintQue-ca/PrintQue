import { createFileRoute } from '@tanstack/react-router'
import { FileText, Layers, Library, Loader2, Printer, TrendingUp } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useFilamentUsage, useStats } from '@/hooks'

export const Route = createFileRoute('/stats')({ component: StatsPage })

function StatsPage() {
  const { data: stats, isLoading } = useStats()
  const { data: filamentData } = useFilamentUsage()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const formatFilament = (grams: number) => {
    if (grams >= 1000) {
      return `${(grams / 1000).toFixed(2)} kg`
    }
    return `${grams} g`
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Statistics</h1>
        <p className="text-muted-foreground">Overview of your print farm performance</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Printers</CardTitle>
            <Printer className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.printers_count || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Connected printers</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Prints</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.active_prints || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Currently printing</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Library</CardTitle>
            <Library className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.library_count || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Total files available</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">In Queue</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.in_queue_count || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Orders actively printing</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Idle Printers</CardTitle>
            <Printer className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.idle_printers || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Ready to print</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Filament Usage</CardTitle>
            <CardDescription>Total filament consumption</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <div className="p-4 bg-primary/10 rounded-lg">
                <Layers className="h-8 w-8 text-primary" />
              </div>
              <div>
                <div className="text-3xl font-bold">
                  {formatFilament(stats?.total_filament || filamentData?.total || 0)}
                </div>
                <p className="text-sm text-muted-foreground">Total filament used</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Completed Today</CardTitle>
            <CardDescription>Prints finished today</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <div className="p-4 bg-green-500/10 rounded-lg">
                <TrendingUp className="h-8 w-8 text-green-500" />
              </div>
              <div>
                <div className="text-3xl font-bold">{stats?.completed_today || 0}</div>
                <p className="text-sm text-muted-foreground">Prints completed today</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
