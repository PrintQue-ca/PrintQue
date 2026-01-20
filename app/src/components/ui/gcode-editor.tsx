import { useState, useMemo, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Info, HelpCircle } from 'lucide-react'

// Common G-code commands used in 3D printing, especially for ejection sequences
const GCODE_REFERENCE: Record<string, { description: string; params?: Record<string, string> }> = {
  // Movement Commands
  'G0': {
    description: 'Rapid linear move - moves to position as fast as possible',
    params: {
      'X': 'Target X position (mm)',
      'Y': 'Target Y position (mm)',
      'Z': 'Target Z position (mm)',
      'E': 'Extruder position (mm)',
      'F': 'Feedrate/speed (mm/min)'
    }
  },
  'G1': {
    description: 'Linear move - moves to position at specified feedrate',
    params: {
      'X': 'Target X position (mm)',
      'Y': 'Target Y position (mm)',
      'Z': 'Target Z position (mm)',
      'E': 'Extruder position (mm)',
      'F': 'Feedrate/speed (mm/min)'
    }
  },
  'G2': {
    description: 'Clockwise arc move',
    params: {
      'X': 'Target X position',
      'Y': 'Target Y position',
      'I': 'X offset to center',
      'J': 'Y offset to center',
      'R': 'Arc radius'
    }
  },
  'G3': {
    description: 'Counter-clockwise arc move',
    params: {
      'X': 'Target X position',
      'Y': 'Target Y position',
      'I': 'X offset to center',
      'J': 'Y offset to center',
      'R': 'Arc radius'
    }
  },
  'G4': {
    description: 'Dwell/pause - waits for specified time',
    params: {
      'P': 'Time in milliseconds',
      'S': 'Time in seconds'
    }
  },
  
  // Homing Commands
  'G28': {
    description: 'Home axes - moves to endstops to calibrate position',
    params: {
      'X': 'Home X axis',
      'Y': 'Home Y axis',
      'Z': 'Home Z axis',
      '(none)': 'Home all axes'
    }
  },
  'G29': {
    description: 'Auto bed leveling - probes the bed surface',
    params: {
      'P': 'Probe mode/pattern',
      'T': 'Topology mode'
    }
  },
  
  // Positioning Commands
  'G90': {
    description: 'Set absolute positioning - coordinates are absolute from origin'
  },
  'G91': {
    description: 'Set relative positioning - coordinates are relative to current position'
  },
  'G92': {
    description: 'Set current position - defines current location without moving',
    params: {
      'X': 'Set X position',
      'Y': 'Set Y position',
      'Z': 'Set Z position',
      'E': 'Set extruder position (often used to reset E to 0)'
    }
  },
  
  // M Commands - Machine Control
  'M0': {
    description: 'Unconditional stop - pauses print until user resumes'
  },
  'M1': {
    description: 'Optional stop - pauses if "stop" switch is pressed'
  },
  'M17': {
    description: 'Enable steppers - powers on stepper motors',
    params: {
      'X': 'Enable X stepper',
      'Y': 'Enable Y stepper',
      'Z': 'Enable Z stepper',
      'E': 'Enable extruder stepper'
    }
  },
  'M18': {
    description: 'Disable steppers - same as M84',
    params: {
      'X': 'Disable X stepper',
      'Y': 'Disable Y stepper',
      'Z': 'Disable Z stepper',
      'E': 'Disable extruder stepper'
    }
  },
  'M82': {
    description: 'Set extruder to absolute mode'
  },
  'M83': {
    description: 'Set extruder to relative mode'
  },
  'M84': {
    description: 'Disable steppers - turns off motor holding current (allows manual movement)',
    params: {
      'S': 'Idle timeout in seconds',
      'X': 'Disable X stepper',
      'Y': 'Disable Y stepper',
      'Z': 'Disable Z stepper',
      'E': 'Disable extruder stepper'
    }
  },
  
  // Temperature Commands
  'M104': {
    description: 'Set hotend temperature - does not wait',
    params: {
      'S': 'Target temperature (°C)',
      'T': 'Tool/extruder number'
    }
  },
  'M105': {
    description: 'Report temperatures - returns current temp readings'
  },
  'M106': {
    description: 'Set fan speed',
    params: {
      'S': 'Fan speed (0-255)',
      'P': 'Fan index'
    }
  },
  'M107': {
    description: 'Turn fan off'
  },
  'M109': {
    description: 'Wait for hotend temperature - blocks until temp reached',
    params: {
      'S': 'Target temperature (°C)',
      'R': 'Wait for temp to reach (cooling or heating)',
      'T': 'Tool/extruder number'
    }
  },
  'M140': {
    description: 'Set bed temperature - does not wait',
    params: {
      'S': 'Target temperature (°C)'
    }
  },
  'M190': {
    description: 'Wait for bed temperature - blocks until temp reached',
    params: {
      'S': 'Target temperature (°C)',
      'R': 'Wait for temp (cooling or heating)'
    }
  },
  
  // Sync/Wait Commands
  'M400': {
    description: 'Wait for moves to finish - ensures all previous commands complete before continuing'
  },
  
  // Filament Commands
  'M600': {
    description: 'Filament change - initiates filament change procedure'
  },
  
  // Print Control
  'M24': {
    description: 'Start/resume print from SD card'
  },
  'M25': {
    description: 'Pause print'
  },
  
  // Beep/Sound
  'M300': {
    description: 'Play tone/beep',
    params: {
      'S': 'Frequency in Hz',
      'P': 'Duration in milliseconds'
    }
  },
  
  // Display
  'M117': {
    description: 'Display message on LCD screen',
    params: {
      '(text)': 'Message to display'
    }
  },
  
  // Acceleration/Jerk
  'M201': {
    description: 'Set max acceleration',
    params: {
      'X': 'Max X acceleration (mm/s²)',
      'Y': 'Max Y acceleration (mm/s²)',
      'Z': 'Max Z acceleration (mm/s²)',
      'E': 'Max extruder acceleration (mm/s²)'
    }
  },
  'M203': {
    description: 'Set max feedrate',
    params: {
      'X': 'Max X feedrate (mm/s)',
      'Y': 'Max Y feedrate (mm/s)',
      'Z': 'Max Z feedrate (mm/s)',
      'E': 'Max extruder feedrate (mm/s)'
    }
  },
  'M204': {
    description: 'Set acceleration',
    params: {
      'P': 'Print acceleration (mm/s²)',
      'R': 'Retract acceleration (mm/s²)',
      'T': 'Travel acceleration (mm/s²)',
      'S': 'Legacy: all acceleration'
    }
  },
  'M205': {
    description: 'Set jerk limits',
    params: {
      'X': 'X jerk (mm/s)',
      'Y': 'Y jerk (mm/s)',
      'Z': 'Z jerk (mm/s)',
      'E': 'Extruder jerk (mm/s)',
      'J': 'Junction deviation'
    }
  },
  
  // Firmware Retract
  'G10': {
    description: 'Firmware retract - retracts filament',
    params: {
      'S': 'Retract length'
    }
  },
  'G11': {
    description: 'Firmware unretract - un-retracts filament'
  },
  
  // Bambu-specific
  'M991': {
    description: 'Bambu: Notify print status'
  },
  'M620': {
    description: 'Bambu: AMS filament settings'
  },
  'M621': {
    description: 'Bambu: AMS filament load'
  },
  'M620.1': {
    description: 'Bambu: AMS purge settings'
  },
  
  // Common Z-offset
  'M851': {
    description: 'Set Z probe offset',
    params: {
      'Z': 'Z offset value (mm)'
    }
  },
  
  // Save Settings
  'M500': {
    description: 'Save settings to EEPROM'
  },
  'M501': {
    description: 'Load settings from EEPROM'
  },
  'M502': {
    description: 'Reset settings to defaults'
  },
  'M503': {
    description: 'Report current settings'
  }
}

interface ParsedLine {
  lineNumber: number
  raw: string
  command: string | null
  params: string[]
  comment: string | null
  isEmpty: boolean
  isCommentOnly: boolean
}

function parseLine(line: string, lineNumber: number): ParsedLine {
  const raw = line
  const trimmed = line.trim()
  
  if (!trimmed) {
    return { lineNumber, raw, command: null, params: [], comment: null, isEmpty: true, isCommentOnly: false }
  }
  
  // Check for comment
  const commentIndex = trimmed.indexOf(';')
  let codePart = trimmed
  let comment: string | null = null
  
  if (commentIndex !== -1) {
    codePart = trimmed.substring(0, commentIndex).trim()
    comment = trimmed.substring(commentIndex + 1).trim()
  }
  
  if (!codePart) {
    return { lineNumber, raw, command: null, params: [], comment, isEmpty: false, isCommentOnly: true }
  }
  
  // Parse command and parameters
  const parts = codePart.split(/\s+/)
  const command = parts[0]?.toUpperCase() || null
  const params = parts.slice(1)
  
  return { lineNumber, raw, command, params, comment, isEmpty: false, isCommentOnly: false }
}

function getCommandInfo(command: string): { description: string; params?: Record<string, string> } | null {
  // Direct match
  if (GCODE_REFERENCE[command]) {
    return GCODE_REFERENCE[command]
  }
  
  // Try without decimal (e.g., M620.1 -> M620)
  const baseCommand = command.split('.')[0]
  if (GCODE_REFERENCE[baseCommand]) {
    return GCODE_REFERENCE[baseCommand]
  }
  
  return null
}

interface GcodeLineProps {
  parsed: ParsedLine
  isSelected: boolean
  onSelect: () => void
}

function GcodeLine({ parsed, isSelected, onSelect }: GcodeLineProps) {
  const [isHovered, setIsHovered] = useState(false)
  const commandInfo = parsed.command ? getCommandInfo(parsed.command) : null
  
  const showTooltip = (isHovered || isSelected) && commandInfo
  
  return (
    <div className="relative group">
      <div
        className={cn(
          "flex items-start gap-2 px-2 py-0.5 font-mono text-xs cursor-pointer transition-colors",
          isSelected ? "bg-primary/10 border-l-2 border-primary" : "hover:bg-muted/50 border-l-2 border-transparent",
          parsed.isEmpty && "opacity-50"
        )}
        onClick={onSelect}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <span className="text-muted-foreground w-8 text-right select-none shrink-0">
          {parsed.lineNumber}
        </span>
        <span className="flex-1 whitespace-pre-wrap break-all">
          {parsed.isEmpty ? (
            <span className="text-muted-foreground">​</span>
          ) : parsed.isCommentOnly ? (
            <span className="text-muted-foreground italic">; {parsed.comment}</span>
          ) : (
            <>
              {parsed.command && (
                <span className={cn(
                  "font-semibold",
                  commandInfo ? "text-blue-600 dark:text-blue-400" : "text-orange-600 dark:text-orange-400"
                )}>
                  {parsed.command}
                </span>
              )}
              {parsed.params.length > 0 && (
                <span className="text-emerald-600 dark:text-emerald-400">
                  {' '}{parsed.params.join(' ')}
                </span>
              )}
              {parsed.comment && (
                <span className="text-muted-foreground italic"> ; {parsed.comment}</span>
              )}
            </>
          )}
        </span>
        {commandInfo && (
          <Info className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-0.5" />
        )}
      </div>
      
      {/* Tooltip */}
      {showTooltip && (
        <div className="absolute left-full top-0 ml-2 z-50 w-72 bg-popover border rounded-md shadow-lg p-3 text-xs">
          <div className="font-semibold text-primary mb-1">{parsed.command}</div>
          <p className="text-foreground mb-2">{commandInfo.description}</p>
          {commandInfo.params && parsed.params.length > 0 && (
            <div className="border-t pt-2 mt-2">
              <div className="font-medium text-muted-foreground mb-1">Parameters used:</div>
              <ul className="space-y-1">
                {parsed.params.map((param, idx) => {
                  const paramLetter = param[0]?.toUpperCase()
                  const paramValue = param.substring(1)
                  const paramDesc = commandInfo.params?.[paramLetter]
                  return (
                    <li key={idx} className="flex gap-2">
                      <span className="font-mono text-emerald-600 dark:text-emerald-400 shrink-0">
                        {paramLetter}{paramValue}
                      </span>
                      {paramDesc && (
                        <span className="text-muted-foreground">— {paramDesc}</span>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface GcodeEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  readOnly?: boolean
  showLineNumbers?: boolean
}

export function GcodeEditor({ 
  value, 
  onChange, 
  placeholder = "; Enter G-code here...",
  className,
  readOnly = false,
  showLineNumbers = true
}: GcodeEditorProps) {
  const [selectedLine, setSelectedLine] = useState<number | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [showReference, setShowReference] = useState(false)
  
  const parsedLines = useMemo(() => {
    const lines = value.split('\n')
    return lines.map((line, idx) => parseLine(line, idx + 1))
  }, [value])
  
  const selectedLineInfo = useMemo(() => {
    if (selectedLine === null) return null
    const parsed = parsedLines.find(p => p.lineNumber === selectedLine)
    if (!parsed?.command) return null
    return { parsed, info: getCommandInfo(parsed.command) }
  }, [selectedLine, parsedLines])
  
  const handleLineSelect = useCallback((lineNumber: number) => {
    setSelectedLine(prev => prev === lineNumber ? null : lineNumber)
  }, [])
  
  if (isEditing || !value.trim()) {
    return (
      <div className={cn("space-y-2", className)}>
        <div className="flex items-center gap-2 justify-end">
          {value.trim() && (
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="text-xs text-primary hover:underline"
            >
              Switch to Visual View
            </button>
          )}
        </div>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          readOnly={readOnly}
          className={cn(
            "w-full min-h-[500px] p-3 font-mono text-xs rounded-md border bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring",
            readOnly && "opacity-75 cursor-not-allowed"
          )}
        />
      </div>
    )
  }
  
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-2 justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowReference(!showReference)}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            <HelpCircle className="h-3 w-3" />
            {showReference ? 'Hide' : 'Show'} Reference
          </button>
        </div>
        {!readOnly && (
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className="text-xs text-primary hover:underline"
          >
            Edit as Text
          </button>
        )}
      </div>
      
      <div className="flex gap-4">
        <div className="flex-1 rounded-md border-2 border-border bg-background overflow-hidden">
          <div className="bg-muted/50 px-3 py-1.5 border-b border-border flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">
              G-code • {parsedLines.length} lines
            </span>
            <span className="text-xs text-muted-foreground">
              Click a line for details
            </span>
          </div>
          <div className="max-h-[60vh] min-h-[400px] overflow-auto scrollbar-thin scrollbar-thumb-muted-foreground/30 scrollbar-track-transparent">
            {parsedLines.map((parsed) => (
              <GcodeLine
                key={parsed.lineNumber}
                parsed={parsed}
                isSelected={selectedLine === parsed.lineNumber}
                onSelect={() => handleLineSelect(parsed.lineNumber)}
              />
            ))}
            {/* Bottom padding to ensure last line is visible */}
            <div className="h-2" />
          </div>
        </div>
        
        {/* Selected Line Details Panel */}
        {selectedLineInfo && (
          <div className="w-64 shrink-0 rounded-md border bg-background p-3">
            <div className="text-xs font-semibold text-primary mb-2">
              Line {selectedLineInfo.parsed.lineNumber}: {selectedLineInfo.parsed.command}
            </div>
            {selectedLineInfo.info ? (
              <>
                <p className="text-xs text-foreground mb-3">
                  {selectedLineInfo.info.description}
                </p>
                {selectedLineInfo.info.params && selectedLineInfo.parsed.params.length > 0 && (
                  <div className="border-t pt-2">
                    <div className="text-xs font-medium text-muted-foreground mb-2">
                      Parameters:
                    </div>
                    <ul className="space-y-1.5">
                      {selectedLineInfo.parsed.params.map((param, idx) => {
                        const paramLetter = param[0]?.toUpperCase()
                        const paramValue = param.substring(1)
                        const paramDesc = selectedLineInfo.info?.params?.[paramLetter]
                        return (
                          <li key={idx} className="text-xs">
                            <span className="font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
                              {paramLetter}
                            </span>
                            <span className="font-mono text-foreground">
                              {paramValue}
                            </span>
                            {paramDesc && (
                              <div className="text-muted-foreground mt-0.5 pl-2">
                                {paramDesc}
                              </div>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground italic">
                Unknown command. This may be a printer-specific or custom command.
              </p>
            )}
          </div>
        )}
      </div>
      
      {/* Reference Panel */}
      {showReference && (
        <div className="rounded-md border bg-muted/30 p-3 max-h-[300px] overflow-auto">
          <div className="text-xs font-semibold mb-3">G-code Quick Reference</div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {Object.entries(GCODE_REFERENCE).slice(0, 30).map(([cmd, info]) => (
              <div key={cmd} className="text-xs p-2 rounded bg-background">
                <span className="font-mono font-semibold text-blue-600 dark:text-blue-400">{cmd}</span>
                <span className="text-muted-foreground ml-2">— {info.description.slice(0, 50)}{info.description.length > 50 ? '...' : ''}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default GcodeEditor
