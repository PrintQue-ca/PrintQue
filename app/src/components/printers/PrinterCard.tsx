import {
  AlertTriangle,
  CheckCircle,
  MoreVertical,
  Pause,
  Play,
  RefreshCw,
  Snowflake,
  Square,
  Thermometer,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Progress } from '@/components/ui/progress'
import { useClearError, useMarkReady, usePausePrint, useResumePrint, useStopPrint } from '@/hooks'
import type { Printer } from '@/types'

interface PrinterCardProps {
  printer: Printer
}

const statusColors: Record<string, string> = {
  IDLE: 'bg-green-500',
  READY: 'bg-green-500',
  PRINTING: 'bg-blue-500',
  FINISHED: 'bg-yellow-500',
  ERROR: 'bg-red-500',
  EJECTING: 'bg-purple-500',
  COOLING: 'bg-cyan-500',
  PAUSED: 'bg-orange-500',
  OFFLINE: 'bg-gray-500',
}

const statusLabels: Record<string, string> = {
  IDLE: 'Idle',
  READY: 'Ready',
  PRINTING: 'Printing',
  FINISHED: 'Finished',
  ERROR: 'Error',
  EJECTING: 'Ejecting',
  COOLING: 'Cooling',
  PAUSED: 'Paused',
  OFFLINE: 'Offline',
}

export function PrinterCard({ printer }: PrinterCardProps) {
  const stopPrint = useStopPrint()
  const pausePrint = usePausePrint()
  const resumePrint = useResumePrint()
  const markReady = useMarkReady()
  const clearError = useClearError()

  const handleStop = () => stopPrint.mutate(printer.name)
  const handlePause = () => pausePrint.mutate(printer.name)
  const handleResume = () => resumePrint.mutate(printer.name)
  const handleMarkReady = () => markReady.mutate(printer.name)
  const handleClearError = () => clearError.mutate(printer.name)

  const isPrinting = printer.status === 'PRINTING'
  const isPaused = printer.status === 'PAUSED'
  const isFinished = printer.status === 'FINISHED'
  const isOffline = printer.status === 'OFFLINE'
  const isError = printer.status === 'ERROR'
  const isCooling = printer.status === 'COOLING'
  const isEjecting = printer.status === 'EJECTING'

  // Show temperatures for all online printers
  const showTemps = !isOffline

  return (
    <Card className="relative">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg">{printer.name}</CardTitle>
            <p className="text-sm text-muted-foreground">{printer.ip}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="capitalize">
              {printer.type}
            </Badge>
            <Badge className={statusColors[printer.status] || 'bg-gray-500'}>
              {statusLabels[printer.status] || printer.status}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isPrinting || isPaused ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="truncate max-w-[200px]">
                {printer.current_file || 'Unknown file'}
              </span>
              <span className="font-medium">{printer.progress || 0}%</span>
            </div>
            <Progress value={printer.progress || 0} className="h-2" />
            {printer.time_remaining !== undefined && (
              <p className="text-xs text-muted-foreground">
                ~{Math.floor(printer.time_remaining / 60)}m remaining
              </p>
            )}
            <div className="flex gap-2 mt-3">
              {isPrinting && (
                <>
                  <Button size="sm" variant="outline" onClick={handlePause}>
                    <Pause className="h-4 w-4 mr-1" />
                    Pause
                  </Button>
                  <Button size="sm" variant="destructive" onClick={handleStop}>
                    <Square className="h-4 w-4 mr-1" />
                    Stop
                  </Button>
                </>
              )}
              {isPaused && (
                <>
                  <Button size="sm" variant="outline" onClick={handleResume}>
                    <Play className="h-4 w-4 mr-1" />
                    Resume
                  </Button>
                  <Button size="sm" variant="destructive" onClick={handleStop}>
                    <Square className="h-4 w-4 mr-1" />
                    Stop
                  </Button>
                </>
              )}
            </div>
          </div>
        ) : isFinished ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Print completed: {printer.current_file || 'Unknown'}
            </p>
            <Button size="sm" onClick={handleMarkReady}>
              <CheckCircle className="h-4 w-4 mr-1" />
              Mark Ready
            </Button>
          </div>
        ) : isCooling ? (
          <div className="space-y-3">
            <div className="rounded-lg bg-gradient-to-r from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 p-3">
              <div className="flex items-center gap-2 mb-2">
                <Snowflake className="h-5 w-5 text-cyan-500 animate-pulse" />
                <span className="font-medium text-cyan-700 dark:text-cyan-300">Cooling Down</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Waiting for bed to cool before ejection...
              </p>
              <div className="flex items-center gap-2 mt-2 text-sm">
                <Thermometer className="h-4 w-4 text-cyan-500" />
                <span>Bed: {(printer.bed_temp ?? 0).toFixed(1)}°C</span>
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={handleMarkReady}>
              <CheckCircle className="h-4 w-4 mr-1" />
              Skip Cooldown
            </Button>
          </div>
        ) : isEjecting ? (
          <div className="space-y-2">
            <div className="rounded-lg bg-purple-500/20 border border-purple-500/30 p-3">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 bg-purple-500 rounded-full animate-pulse" />
                <span className="text-sm font-medium text-purple-700 dark:text-purple-300">
                  Running ejection sequence...
                </span>
              </div>
            </div>
          </div>
        ) : isError ? (
          <div className="space-y-3">
            {/* Error Alert Box */}
            <div className="rounded-md bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-red-800 dark:text-red-200">
                    Printer Error
                  </p>
                  <p className="text-sm text-red-700 dark:text-red-300 mt-1 break-all">
                    {printer.error_message || 'Unknown error - check printer display'}
                  </p>
                  {/* Show HMS alerts if available (Bambu printers) */}
                  {printer.hms_alerts && printer.hms_alerts.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <p className="text-xs font-medium text-red-600 dark:text-red-400">
                        HMS Alerts:
                      </p>
                      <ul className="text-xs text-red-600 dark:text-red-400 list-disc list-inside">
                        {printer.hms_alerts.map((alert, index) => (
                          <li key={index} className="break-all">
                            {alert}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={handleClearError}
                disabled={clearError.isPending}
                className="flex-1"
              >
                <RefreshCw
                  className={`h-4 w-4 mr-1 ${clearError.isPending ? 'animate-spin' : ''}`}
                />
                {clearError.isPending ? 'Clearing...' : 'Clear Error'}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Clear error to mark printer as ready and resume queue processing
            </p>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Ready for printing</p>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>Edit</DropdownMenuItem>
                <DropdownMenuItem className="text-destructive">Delete</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}

        {/* Temperature display */}
        {showTemps && (
          <div className="flex items-center gap-4 mt-3 pt-3 border-t text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <Thermometer className="h-3 w-3" />
              <span>Nozzle: {(printer.nozzle_temp ?? 0).toFixed(1)}°C</span>
            </div>
            <div className="flex items-center gap-1">
              <span>Bed: {(printer.bed_temp ?? 0).toFixed(1)}°C</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default PrinterCard
