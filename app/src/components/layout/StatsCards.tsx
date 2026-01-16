import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Printer, FileText, Layers, Pause, Play } from 'lucide-react'
import { useStats, useEjectionStatus, usePauseEjection, useResumeEjection } from '@/hooks'

export function StatsCards() {
  const { data: stats, isLoading: statsLoading } = useStats()
  const { data: ejectionStatus } = useEjectionStatus()
  const pauseEjection = usePauseEjection()
  const resumeEjection = useResumeEjection()

  const handleToggleEjection = () => {
    if (ejectionStatus?.paused) {
      resumeEjection.mutate()
    } else {
      pauseEjection.mutate()
    }
  }

  if (statsLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i} className="animate-pulse">
            <CardHeader className="pb-2">
              <div className="h-4 bg-muted rounded w-24" />
            </CardHeader>
            <CardContent>
              <div className="h-8 bg-muted rounded w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Printers</CardTitle>
          <Printer className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.printers_count || 0}</div>
          <p className="text-xs text-muted-foreground">
            {stats?.idle_printers || 0} idle, {stats?.active_prints || 0} printing
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">In Queue</CardTitle>
          <FileText className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats?.in_queue_count || 0}</div>
          <p className="text-xs text-muted-foreground">
            Orders actively printing
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Filament Used</CardTitle>
          <Layers className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats?.total_filament 
              ? `${(stats.total_filament / 1000).toFixed(1)}kg`
              : '0g'}
          </div>
          <p className="text-xs text-muted-foreground">
            Total filament consumption
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Ejection Status</CardTitle>
          {ejectionStatus?.paused ? (
            <Pause className="h-4 w-4 text-yellow-500" />
          ) : (
            <Play className="h-4 w-4 text-green-500" />
          )}
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold">
                {ejectionStatus?.paused ? 'Paused' : 'Active'}
              </div>
              <p className="text-xs text-muted-foreground">
                Auto-ejection {ejectionStatus?.paused ? 'disabled' : 'enabled'}
              </p>
            </div>
            <Button
              size="sm"
              variant={ejectionStatus?.paused ? 'default' : 'secondary'}
              onClick={handleToggleEjection}
              disabled={pauseEjection.isPending || resumeEjection.isPending}
            >
              {ejectionStatus?.paused ? (
                <>
                  <Play className="h-4 w-4 mr-1" />
                  Resume
                </>
              ) : (
                <>
                  <Pause className="h-4 w-4 mr-1" />
                  Pause
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default StatsCards
