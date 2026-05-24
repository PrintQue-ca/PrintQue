import {
  ChevronDown,
  ChevronUp,
  FileCode,
  FolderOpen,
  Plus,
  Save,
  Thermometer,
  Trash2,
  Upload,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { GcodeEditor } from '@/components/ui/gcode-editor'
import { Input } from '@/components/ui/input'
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
  useCreateLibraryItem,
  useDefaultEjectionSettings,
  useEjectionCodes,
  useGroups,
  useSaveDefaultEjectionSettings,
} from '@/hooks'

export function AddToLibraryForm() {
  const [file, setFile] = useState<File | null>(null)
  const [orderName, setOrderName] = useState('')
  const [selectedGroups, setSelectedGroups] = useState<number[]>([])
  const [ejectionEnabled, setEjectionEnabled] = useState(false)
  const [endGcode, setEndGcode] = useState('')
  const [showEjectionSection, setShowEjectionSection] = useState(false)
  const [selectedEjectionCodeId, setSelectedEjectionCodeId] = useState<string>('custom')
  const [cooldownTemp, setCooldownTemp] = useState<string>('')
  const [isGcodeDialogOpen, setIsGcodeDialogOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const gcodeFileInputRef = useRef<HTMLInputElement>(null)
  const gcodeDialogFileInputRef = useRef<HTMLInputElement>(null)

  const createLibraryItem = useCreateLibraryItem()
  const { data: groups } = useGroups()
  const { data: defaultSettings } = useDefaultEjectionSettings()
  const saveDefaultSettings = useSaveDefaultEjectionSettings()
  const { data: ejectionCodes } = useEjectionCodes()

  // Load default settings when they change
  useEffect(() => {
    if (!defaultSettings) return
    setEjectionEnabled(defaultSettings.ejection_enabled)
    if (defaultSettings.ejection_code_id) {
      setSelectedEjectionCodeId('default')
      const preset = ejectionCodes?.find((code) => code.id === defaultSettings.ejection_code_id)
      if (preset) {
        setEndGcode(preset.gcode)
      }
    }
  }, [defaultSettings, ejectionCodes])

  // Handle ejection code selection
  const handleEjectionCodeSelect = (codeId: string) => {
    setSelectedEjectionCodeId(codeId)

    if (codeId === 'custom') {
      return
    }

    if (codeId === 'default') {
      const defaultId = defaultSettings?.ejection_code_id
      const preset = defaultId ? ejectionCodes?.find((code) => code.id === defaultId) : undefined
      setEndGcode(preset?.gcode || '')
      return
    }

    const selectedCode = ejectionCodes?.find((code) => code.id === codeId)
    if (selectedCode) {
      setEndGcode(selectedCode.gcode)
      toast.success(`Loaded "${selectedCode.name}" ejection code`)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      // Check for valid file types
      const validExtensions = ['.gcode', '.3mf', '.stl']
      const hasValidExt = validExtensions.some((ext) =>
        selectedFile.name.toLowerCase().endsWith(ext)
      )
      if (!hasValidExt) {
        toast.error('Please select a valid print file (.gcode, .3mf, .stl)')
        return
      }
      setFile(selectedFile)
    }
  }

  const handleGcodeFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      const validExtensions = ['.txt', '.gcode', '.gc', '.nc']
      const hasValidExt = validExtensions.some((ext) =>
        selectedFile.name.toLowerCase().endsWith(ext)
      )
      if (!hasValidExt) {
        toast.error('Please select a valid G-code file (.txt, .gcode, .gc, .nc)')
        return
      }
      // Read the file contents
      const reader = new FileReader()
      reader.onload = (event) => {
        const content = event.target?.result as string
        setEndGcode(content)
        toast.success(`Loaded G-code from ${selectedFile.name}`)
      }
      reader.onerror = () => {
        toast.error('Failed to read file')
      }
      reader.readAsText(selectedFile)
    }
  }

  const handleGcodeDialogFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      const validExtensions = ['.txt', '.gcode', '.gc', '.nc']
      const hasValidExt = validExtensions.some((ext) =>
        selectedFile.name.toLowerCase().endsWith(ext)
      )
      if (!hasValidExt) {
        toast.error('Please select a valid G-code file (.txt, .gcode, .gc, .nc)')
        return
      }
      const reader = new FileReader()
      reader.onload = (event) => {
        const content = event.target?.result as string
        setEndGcode(content)
        setSelectedEjectionCodeId('custom')
        toast.success(`Loaded G-code from ${selectedFile.name}`)
      }
      reader.onerror = () => toast.error('Failed to read file')
      reader.readAsText(selectedFile)
    }
  }

  const endGcodeLineCount = endGcode.trim() ? endGcode.trim().split('\n').length : 0

  const handleSaveAsDefault = async () => {
    try {
      const payload: { ejection_enabled: boolean; ejection_code_id?: string; end_gcode?: string } =
        {
          ejection_enabled: ejectionEnabled,
        }
      if (selectedEjectionCodeId === 'custom') {
        payload.end_gcode = endGcode
      } else if (selectedEjectionCodeId === 'default' && defaultSettings?.ejection_code_id) {
        payload.ejection_code_id = defaultSettings.ejection_code_id
      } else if (selectedEjectionCodeId !== 'custom' && selectedEjectionCodeId !== 'default') {
        payload.ejection_code_id = selectedEjectionCodeId
      } else if (endGcode) {
        payload.end_gcode = endGcode
      }
      await saveDefaultSettings.mutateAsync(payload)
      toast.success('Default ejection settings saved')
    } catch {
      toast.error('Failed to save default settings')
    }
  }

  const handleClearGcode = () => {
    setEndGcode('')
    toast.info('Ejection G-code cleared')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!file) {
      toast.error('Please select a file')
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    if (orderName.trim()) {
      formData.append('name', orderName.trim())
    }
    if (selectedGroups.length > 0) {
      formData.append('groups', JSON.stringify(selectedGroups))
    }
    formData.append('ejection_enabled', ejectionEnabled.toString())
    if (ejectionEnabled) {
      if (selectedEjectionCodeId && selectedEjectionCodeId !== 'custom') {
        formData.append('ejection_code_id', selectedEjectionCodeId)
      } else if (endGcode) {
        formData.append('end_gcode', endGcode)
      }
    }

    // Add cooldown temperature if set (for Bambu printers)
    if (ejectionEnabled && cooldownTemp) {
      const tempValue = parseInt(cooldownTemp, 10)
      if (!Number.isNaN(tempValue) && tempValue >= 0 && tempValue <= 100) {
        formData.append('cooldown_temp', tempValue.toString())
      }
    }

    try {
      await createLibraryItem.mutateAsync(formData)
      toast.success('Added to library', { duration: 2000 })
      setFile(null)
      setOrderName('')
      setSelectedGroups([])
      setCooldownTemp('')
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    } catch {
      toast.error('Failed to add to library')
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) {
      const validExtensions = ['.gcode', '.3mf', '.stl']
      const hasValidExt = validExtensions.some((ext) =>
        droppedFile.name.toLowerCase().endsWith(ext)
      )
      if (hasValidExt) {
        setFile(droppedFile)
      } else {
        toast.error('Please drop a valid print file (.gcode, .3mf, .stl)')
      }
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Add to Library</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onClick={() => fileInputRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".gcode,.3mf,.stl"
                onChange={handleFileChange}
                className="hidden"
              />
              <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
              {file ? (
                <p className="text-sm font-medium">{file.name}</p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Click or drag to upload .gcode, .3mf, or .stl
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="orderName">Order Name (optional)</Label>
              <Input
                id="orderName"
                type="text"
                placeholder="e.g., Test with ejection v2"
                value={orderName}
                onChange={(e) => setOrderName(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Custom name for this library item. If empty, filename is used.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="groups">Printer Group</Label>
              <Select
                value={selectedGroups.length > 0 ? selectedGroups[0].toString() : 'all'}
                onValueChange={(value) => {
                  if (value === 'all') {
                    setSelectedGroups([])
                  } else {
                    setSelectedGroups([parseInt(value, 10)])
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All printers" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All printers</SelectItem>
                  {groups?.map((group) => (
                    <SelectItem key={group.id} value={group.id.toString()}>
                      {group.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Ejection Settings */}
            <div className="space-y-3 border-t pt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Switch
                    id="ejection"
                    checked={ejectionEnabled}
                    onCheckedChange={setEjectionEnabled}
                  />
                  <Label htmlFor="ejection" className="cursor-pointer">
                    Enable Auto-Ejection
                  </Label>
                </div>
                {ejectionEnabled && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowEjectionSection(!showEjectionSection)}
                  >
                    {showEjectionSection ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </Button>
                )}
              </div>

              {ejectionEnabled && showEjectionSection && (
                <div className="space-y-3">
                  {/* Ejection Code Selector */}
                  <div className="space-y-2">
                    <Label>Select Ejection Code</Label>
                    <Select value={selectedEjectionCodeId} onValueChange={handleEjectionCodeSelect}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select an ejection code" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="default">
                          <div className="flex items-center">
                            <FolderOpen className="h-4 w-4 mr-2 text-muted-foreground" />
                            Default Settings
                          </div>
                        </SelectItem>
                        <SelectItem value="custom">
                          <div className="flex items-center">
                            <FileCode className="h-4 w-4 mr-2 text-muted-foreground" />
                            Custom (enter below)
                          </div>
                        </SelectItem>
                        {ejectionCodes && ejectionCodes.length > 0 && (
                          <>
                            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t mt-1 pt-1">
                              Saved Ejection Codes
                            </div>
                            {ejectionCodes.map((code) => (
                              <SelectItem key={code.id} value={code.id}>
                                {code.name}
                              </SelectItem>
                            ))}
                          </>
                        )}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Choose a saved ejection code or enter custom G-code below.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label>End G-code</Label>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="rounded-md border bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                        {endGcodeLineCount === 0
                          ? 'No G-code'
                          : `${endGcodeLineCount} line${endGcodeLineCount === 1 ? '' : 's'}`}
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setIsGcodeDialogOpen(true)}
                      >
                        <FileCode className="h-4 w-4 mr-1" />
                        View / Edit G-code
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => gcodeFileInputRef.current?.click()}
                      >
                        <Upload className="h-4 w-4 mr-1" />
                        Upload File
                      </Button>
                      <input
                        ref={gcodeFileInputRef}
                        type="file"
                        accept=".txt,.gcode,.gc,.nc"
                        onChange={handleGcodeFileChange}
                        className="hidden"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Opens the G-code editor with line-by-line explanation. Upload or edit there.
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleSaveAsDefault}
                      disabled={saveDefaultSettings.isPending}
                    >
                      <Save className="h-4 w-4 mr-1" />
                      Save as Default
                    </Button>
                    <Button type="button" variant="outline" size="sm" onClick={handleClearGcode}>
                      <Trash2 className="h-4 w-4 mr-1" />
                      Clear
                    </Button>
                  </div>

                  {/* Cooldown Temperature (Bambu printers only) */}
                  <div className="mt-4 p-3 border rounded-lg bg-muted/50">
                    <div className="flex items-center gap-2 mb-2">
                      <Thermometer className="h-4 w-4 text-cyan-500" />
                      <Label className="text-sm font-medium">
                        Cooldown Temperature (Bambu only)
                      </Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        placeholder="Optional"
                        value={cooldownTemp}
                        onChange={(e) => setCooldownTemp(e.target.value)}
                        className="w-24"
                      />
                      <span className="text-sm text-muted-foreground">°C</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">
                      If set, PrintQue will wait for the bed to cool to this temperature before
                      running the ejection G-code on Bambu printers.
                    </p>
                  </div>
                </div>
              )}
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={!file || createLibraryItem.isPending}
            >
              <Plus className="h-4 w-4 mr-2" />
              {createLibraryItem.isPending ? 'Adding...' : 'Add to Library'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* End G-code editor dialog (explainer + full edit) */}
      <Dialog open={isGcodeDialogOpen} onOpenChange={setIsGcodeDialogOpen}>
        <DialogContent className="flex max-h-[90vh] w-[90vw] max-w-6xl flex-col">
          <DialogHeader className="shrink-0">
            <DialogTitle>End G-code</DialogTitle>
            <DialogDescription>
              View or edit the ejection G-code. Click a line to see what each command does.
            </DialogDescription>
          </DialogHeader>
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
            <div className="flex shrink-0 justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => gcodeDialogFileInputRef.current?.click()}
              >
                <Upload className="h-4 w-4 mr-1" />
                Upload File
              </Button>
              <input
                ref={gcodeDialogFileInputRef}
                type="file"
                accept=".txt,.gcode,.gc,.nc"
                onChange={handleGcodeDialogFileChange}
                className="hidden"
              />
            </div>
            <div className="min-h-0 flex-1 overflow-hidden">
              <GcodeEditor
                value={endGcode}
                onChange={(value) => {
                  setEndGcode(value)
                  setSelectedEjectionCodeId('custom')
                }}
                placeholder="G90&#10;M211 X0 Y0 Z0&#10;G1 X60 Z1 F6000&#10;G1 Y300 F6000&#10;G1 Y-4 F300&#10;M400&#10;M211 S1"
                className="h-full min-h-0"
              />
            </div>
          </div>
          <DialogFooter className="shrink-0">
            <Button type="button" variant="outline" onClick={() => setIsGcodeDialogOpen(false)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/** @deprecated Use AddToLibraryForm */
export const NewOrderForm = AddToLibraryForm

export default AddToLibraryForm
