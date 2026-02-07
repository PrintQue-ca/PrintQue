import { createFileRoute } from '@tanstack/react-router'
import {
  Bug,
  Clock,
  Copy,
  Cpu,
  FileText,
  HardDrive,
  Loader2,
  Server,
  Settings2,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  useLoggingConfig,
  useLogsPath,
  useSetDebugFlag,
  useSetLogLevel,
  useSystemInfo,
} from '@/hooks'

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
        <p className="text-muted-foreground">Server and application status</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Version</CardTitle>
            <Server className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{systemInfo?.version || 'N/A'}</div>
            <p className="text-xs text-muted-foreground mt-1">PrintQue version</p>
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
            <p className="text-xs text-muted-foreground mt-1">Server uptime</p>
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
            <p className="text-xs text-muted-foreground mt-1">Memory usage</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CPU</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemInfo?.cpu_usage !== undefined ? `${systemInfo.cpu_usage.toFixed(1)}%` : 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">CPU usage</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Environment</CardTitle>
          <CardDescription>Server environment details</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 md:grid-cols-2">
            <div className="border rounded-lg p-4">
              <dt className="text-sm text-muted-foreground">Python Version</dt>
              <dd className="text-lg font-medium mt-1">{systemInfo?.python_version || 'N/A'}</dd>
            </div>
            <div className="border rounded-lg p-4">
              <dt className="text-sm text-muted-foreground">Platform</dt>
              <dd className="text-lg font-medium mt-1">{systemInfo?.platform || 'N/A'}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Logging Settings */}
      <LoggingSettings />

      {/* Logs for debugging (when running without console) */}
      <LogsForDebugging />

      <Card>
        <CardHeader>
          <CardTitle>About PrintQue</CardTitle>
          <CardDescription>Print queue management system</CardDescription>
        </CardHeader>
        <CardContent className="prose prose-sm dark:prose-invert max-w-none">
          <p>
            PrintQue is a print queue management system designed for 3D print farms. It supports
            multiple printer types including Bambu Lab, Prusa, and OctoPrint-compatible printers.
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

// Logging Settings Component
function LoggingSettings() {
  const { data: config, isLoading } = useLoggingConfig()
  const setLogLevel = useSetLogLevel()
  const setDebugFlag = useSetDebugFlag()

  const handleLevelChange = async (level: string) => {
    try {
      await setLogLevel.mutateAsync(level)
      toast.success(`Log level set to ${level}`)
    } catch {
      toast.error('Failed to set log level')
    }
  }

  const handleFlagToggle = async (flag: string, enabled: boolean) => {
    try {
      await setDebugFlag.mutateAsync({ flag, enabled })
      toast.success(`Debug flag '${flag}' ${enabled ? 'enabled' : 'disabled'}`)
    } catch {
      toast.error('Failed to update debug flag')
    }
  }

  const debugFlagDescriptions: Record<string, string> = {
    cooldown: 'Temperature waiting before ejection',
    ejection: 'Ejection process details',
    distribution: 'Job distribution logic',
    mqtt: 'MQTT/Bambu communication',
    state: 'Printer state transitions',
    api: 'API request/response details',
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5" />
            Logging Settings
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Settings2 className="h-5 w-5" />
          Logging Settings
        </CardTitle>
        <CardDescription>
          Control console log verbosity and enable feature-specific debugging
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Log Level */}
        <div className="space-y-2">
          <Label htmlFor="log-level">Console Log Level</Label>
          <Select
            value={config?.console_level || 'INFO'}
            onValueChange={handleLevelChange}
            disabled={setLogLevel.isPending}
          >
            <SelectTrigger id="log-level" className="w-[200px]">
              <SelectValue placeholder="Select level" />
            </SelectTrigger>
            <SelectContent>
              {(config?.available_levels || ['DEBUG', 'INFO', 'WARNING', 'ERROR']).map((level) => (
                <SelectItem key={level} value={level}>
                  {level}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            DEBUG shows all messages, INFO shows standard operation, WARNING shows only issues
          </p>
        </div>

        {/* Debug Flags */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Bug className="h-4 w-4 text-muted-foreground" />
            <Label>Debug Flags</Label>
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            Enable verbose logging for specific features without changing the overall log level
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {config?.available_flags?.map((flag) => (
              <div key={flag} className="flex items-center justify-between p-3 border rounded-lg">
                <div>
                  <Label htmlFor={`flag-${flag}`} className="font-medium capitalize">
                    {flag}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {debugFlagDescriptions[flag] || 'Enable debug logging'}
                  </p>
                </div>
                <Switch
                  id={`flag-${flag}`}
                  checked={config?.debug_flags?.[flag] || false}
                  onCheckedChange={(checked) => handleFlagToggle(flag, checked)}
                  disabled={setDebugFlag.isPending}
                />
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-muted-foreground pt-2 border-t">
          Settings are saved automatically and persist across restarts. File logs always capture
          DEBUG level.
        </p>
      </CardContent>
    </Card>
  )
}

// Logs for debugging when the app runs in the background (no console window)
function LogsForDebugging() {
  const { data: logsPath, isLoading } = useLogsPath()

  const copyPath = (path: string) => {
    navigator.clipboard.writeText(path)
    toast.success('Path copied to clipboard')
  }

  const downloadUrl = import.meta.env.DEV
    ? 'http://localhost:5000/api/v1/system/logs/download'
    : '/api/v1/system/logs/download'

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Logs for debugging
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Logs for debugging
        </CardTitle>
        <CardDescription>
          When the app runs in the background (no console window), all logs are written to files.
          Use these for troubleshooting.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label className="text-muted-foreground">Log folder</Label>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded border bg-muted/50 px-3 py-2 text-sm break-all">
              {logsPath?.log_dir ?? '—'}
            </code>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => logsPath && copyPath(logsPath.log_dir)}
              title="Copy path"
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Main server log: <code className="rounded bg-muted px-1">app.log</code> — Detailed logs:{' '}
          <code className="rounded bg-muted px-1">logs/</code> folder (printque.log,
          state_changes.log, etc.)
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="default" asChild>
            <a href={downloadUrl} download target="_blank" rel="noopener noreferrer">
              Download recent logs (last 15 min)
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
