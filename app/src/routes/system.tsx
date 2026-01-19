import { createFileRoute } from '@tanstack/react-router'
import { useSystemInfo } from '@/hooks'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Loader2, Server, Cpu, HardDrive, Clock } from 'lucide-react'
import { EjectionCodesManager } from '@/components/orders/EjectionCodesManager'

export const Route = createFileRoute('/system')({ component: SystemPage })

function SystemPage() {
  const { data: systemInfo, isLoading } = useSystemInfo()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    
    if (days > 0) {
      return `${days}d ${hours}h ${minutes}m`
    }
    if (hours > 0) {
      return `${hours}h ${minutes}m`
    }
    return `${minutes}m`
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">System Information</h1>
        <p className="text-muted-foreground">
          Server and application status
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Version</CardTitle>
            <Server className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{systemInfo?.version || 'N/A'}</div>
            <p className="text-xs text-muted-foreground mt-1">
              PrintQue version
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Uptime</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemInfo?.uptime ? formatUptime(systemInfo.uptime) : 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Server uptime
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Memory</CardTitle>
            <HardDrive className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemInfo?.memory_usage !== undefined 
                ? `${systemInfo.memory_usage.toFixed(1)}%`
                : 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Memory usage
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CPU</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemInfo?.cpu_usage !== undefined 
                ? `${systemInfo.cpu_usage.toFixed(1)}%`
                : 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              CPU usage
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Environment</CardTitle>
          <CardDescription>
            Server environment details
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 md:grid-cols-2">
            <div className="border rounded-lg p-4">
              <dt className="text-sm text-muted-foreground">Python Version</dt>
              <dd className="text-lg font-medium mt-1">
                {systemInfo?.python_version || 'N/A'}
              </dd>
            </div>
            <div className="border rounded-lg p-4">
              <dt className="text-sm text-muted-foreground">Platform</dt>
              <dd className="text-lg font-medium mt-1">
                {systemInfo?.platform || 'N/A'}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Ejection Codes Manager */}
      <EjectionCodesManager />

      <Card>
        <CardHeader>
          <CardTitle>About PrintQue</CardTitle>
          <CardDescription>
            Print queue management system
          </CardDescription>
        </CardHeader>
        <CardContent className="prose prose-sm dark:prose-invert max-w-none">
          <p>
            PrintQue is a print queue management system designed for 3D print farms.
            It supports multiple printer types including Bambu Lab, Prusa, and OctoPrint-compatible printers.
          </p>
          <p>
            Features include automatic print job distribution, real-time status monitoring,
            auto-ejection support, and printer grouping for organized workflow management.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
