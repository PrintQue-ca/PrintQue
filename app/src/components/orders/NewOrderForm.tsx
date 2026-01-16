import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Upload, Plus, FileCode, Save, Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import { useCreateOrder, useGroups, useDefaultEjectionSettings, useSaveDefaultEjectionSettings } from '@/hooks'
import { toast } from 'sonner'

export function NewOrderForm() {
  const [file, setFile] = useState<File | null>(null)
  const [quantity, setQuantity] = useState(1)
  const [selectedGroups, setSelectedGroups] = useState<number[]>([])
  const [ejectionEnabled, setEjectionEnabled] = useState(false)
  const [endGcode, setEndGcode] = useState('')
  const [showEjectionSection, setShowEjectionSection] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const gcodeFileInputRef = useRef<HTMLInputElement>(null)
  
  const createOrder = useCreateOrder()
  const { data: groups } = useGroups()
  const { data: defaultSettings } = useDefaultEjectionSettings()
  const saveDefaultSettings = useSaveDefaultEjectionSettings()

  // Load default settings when they change
  useEffect(() => {
    if (defaultSettings) {
      setEjectionEnabled(defaultSettings.ejection_enabled)
      setEndGcode(defaultSettings.end_gcode)
    }
  }, [defaultSettings])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      // Check for valid file types
      const validExtensions = ['.gcode', '.3mf', '.stl']
      const hasValidExt = validExtensions.some(ext => 
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
      const hasValidExt = validExtensions.some(ext => 
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

  const handleGcodeDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) {
      const validExtensions = ['.txt', '.gcode', '.gc', '.nc']
      const hasValidExt = validExtensions.some(ext => 
        droppedFile.name.toLowerCase().endsWith(ext)
      )
      if (hasValidExt) {
        const reader = new FileReader()
        reader.onload = (event) => {
          const content = event.target?.result as string
          setEndGcode(content)
          toast.success(`Loaded G-code from ${droppedFile.name}`)
        }
        reader.readAsText(droppedFile)
      } else {
        toast.error('Please drop a valid G-code file (.txt, .gcode, .gc, .nc)')
      }
    }
  }

  const handleSaveAsDefault = async () => {
    try {
      await saveDefaultSettings.mutateAsync({
        ejection_enabled: ejectionEnabled,
        end_gcode: endGcode
      })
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
    formData.append('quantity', quantity.toString())
    if (selectedGroups.length > 0) {
      formData.append('groups', JSON.stringify(selectedGroups))
    }
    formData.append('ejection_enabled', ejectionEnabled.toString())
    if (ejectionEnabled && endGcode) {
      formData.append('end_gcode', endGcode)
    }

    try {
      await createOrder.mutateAsync(formData)
      toast.success('Order added to library')
      // Reset form
      setFile(null)
      setQuantity(1)
      setSelectedGroups([])
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    } catch {
      toast.error('Failed to create order')
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) {
      const validExtensions = ['.gcode', '.3mf', '.stl']
      const hasValidExt = validExtensions.some(ext => 
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
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Add New Order</CardTitle>
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

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="quantity">Quantity</Label>
              <Input
                id="quantity"
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="groups">Printer Group</Label>
              <Select
                value={selectedGroups.length > 0 ? selectedGroups[0].toString() : 'all'}
                onValueChange={(value) => {
                  if (value === 'all') {
                    setSelectedGroups([])
                  } else {
                    setSelectedGroups([parseInt(value)])
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
                <div className="space-y-2">
                  <Label>Custom End G-code</Label>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => gcodeFileInputRef.current?.click()}
                    >
                      <FileCode className="h-4 w-4 mr-1" />
                      Upload
                    </Button>
                    <input
                      ref={gcodeFileInputRef}
                      type="file"
                      accept=".txt,.gcode,.gc,.nc"
                      onChange={handleGcodeFileChange}
                      className="hidden"
                    />
                  </div>
                  <Textarea
                    value={endGcode}
                    onChange={(e) => setEndGcode(e.target.value)}
                    onDrop={handleGcodeDrop}
                    onDragOver={(e) => e.preventDefault()}
                    placeholder="G28 X Y&#10;M84"
                    rows={4}
                    className="font-mono text-xs"
                  />
                  <p className="text-xs text-muted-foreground">
                    This G-code runs after print completion. Drag and drop a file or type directly.
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
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleClearGcode}
                  >
                    <Trash2 className="h-4 w-4 mr-1" />
                    Clear
                  </Button>
                </div>
              </div>
            )}
          </div>

          <Button 
            type="submit" 
            className="w-full" 
            disabled={!file || createOrder.isPending}
          >
            <Plus className="h-4 w-4 mr-2" />
            {createOrder.isPending ? 'Adding...' : 'Add to Library'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

export default NewOrderForm
