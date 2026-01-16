import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { MoreVertical, Play, Pause, Square, CheckCircle } from 'lucide-react'
import type { Printer } from '@/types'
import { useStopPrint, usePausePrint, useResumePrint, useMarkReady } from '@/hooks'

interface PrinterCardProps {
  printer: Printer
}

const statusColors: Record<string, string> = {
  IDLE: 'bg-green-500',
  PRINTING: 'bg-blue-500',
  FINISHED: 'bg-yellow-500',
  ERROR: 'bg-red-500',
  EJECTING: 'bg-purple-500',
  PAUSED: 'bg-orange-500',
  OFFLINE: 'bg-gray-500',
}

const statusLabels: Record<string, string> = {
  IDLE: 'Idle',
  PRINTING: 'Printing',
  FINISHED: 'Finished',
  ERROR: 'Error',
  EJECTING: 'Ejecting',
  PAUSED: 'Paused',
  OFFLINE: 'Offline',
}

export function PrinterCard({ printer }: PrinterCardProps) {
  const stopPrint = useStopPrint()
  const pausePrint = usePausePrint()
  const resumePrint = useResumePrint()
  const markReady = useMarkReady()

  const handleStop = () => stopPrint.mutate(printer.name)
  const handlePause = () => pausePrint.mutate(printer.name)
  const handleResume = () => resumePrint.mutate(printer.name)
  const handleMarkReady = () => markReady.mutate(printer.name)

  const isPrinting = printer.status === 'PRINTING'
  const isPaused = printer.status === 'PAUSED'
  const isFinished = printer.status === 'FINISHED'

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
              <span className="truncate max-w-[200px]">{printer.current_file || 'Unknown file'}</span>
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
      </CardContent>
    </Card>
  )
}

export default PrinterCard
