import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { GcodeEditor } from '@/components/ui/gcode-editor'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Upload, Plus, FileCode, Trash2, Code, Edit2, Play } from 'lucide-react'
import { 
  useEjectionCodes, 
  useCreateEjectionCode, 
  useUploadEjectionCode, 
  useDeleteEjectionCode,
  useUpdateEjectionCode,
  useTestEjectionCode,
  usePrinters
} from '@/hooks'
import { toast } from 'sonner'
import type { EjectionCode } from '@/types'

export function EjectionCodesManager() {
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isViewOpen, setIsViewOpen] = useState(false)
  const [isTestOpen, setIsTestOpen] = useState(false)
  const [viewingCode, setViewingCode] = useState<EjectionCode | null>(null)
  const [editedName, setEditedName] = useState('')
  const [editedGcode, setEditedGcode] = useState('')
  const [testingCode, setTestingCode] = useState<EjectionCode | null>(null)
  const [selectedPrinter, setSelectedPrinter] = useState<string>('')
  const [newName, setNewName] = useState('')
  const [newGcode, setNewGcode] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const editFileInputRef = useRef<HTMLInputElement>(null)
  
  const { data: ejectionCodes, isLoading } = useEjectionCodes()
  const { data: printers } = usePrinters()
  const createCode = useCreateEjectionCode()
  const uploadCode = useUploadEjectionCode()
  const deleteCode = useDeleteEjectionCode()
  const updateCode = useUpdateEjectionCode()
  const testCode = useTestEjectionCode()
  
  // Filter printers that are available for testing (IDLE, READY, or FINISHED)
  const availablePrinters = printers?.filter(p => 
    ['IDLE', 'READY', 'FINISHED', 'OPERATIONAL'].includes(p.status?.toUpperCase() || '')
  ) || []

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const validExtensions = ['.txt', '.gcode', '.gc', '.nc']
    const hasValidExt = validExtensions.some(ext => 
      file.name.toLowerCase().endsWith(ext)
    )
    if (!hasValidExt) {
      toast.error('Please select a valid G-code file (.txt, .gcode, .gc, .nc)')
      return
    }

    // Read file to populate the textarea
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target?.result as string
      setNewGcode(content)
      // Auto-populate name from filename if empty
      if (!newName) {
        const nameFromFile = file.name.replace(/\.(txt|gcode|gc|nc)$/i, '')
        setNewName(nameFromFile)
      }
      toast.success(`Loaded G-code from ${file.name}`)
    }
    reader.onerror = () => {
      toast.error('Failed to read file')
    }
    reader.readAsText(file)
  }

  const handleCreate = async () => {
    if (!newName.trim()) {
      toast.error('Please enter a name')
      return
    }
    if (!newGcode.trim()) {
      toast.error('Please enter the G-code content')
      return
    }

    try {
      await createCode.mutateAsync({
        name: newName.trim(),
        gcode: newGcode.trim()
      })
      toast.success(`Ejection code "${newName}" created`)
      setIsCreateOpen(false)
      setNewName('')
      setNewGcode('')
    } catch {
      toast.error('Failed to create ejection code')
    }
  }

  const handleDelete = async (code: EjectionCode) => {
    if (!confirm(`Delete "${code.name}"? This cannot be undone.`)) return
    
    try {
      await deleteCode.mutateAsync(code.id)
      toast.success(`Deleted "${code.name}"`)
    } catch {
      toast.error('Failed to delete ejection code')
    }
  }

  const handleView = (code: EjectionCode) => {
    setViewingCode(code)
    setEditedName(code.name)
    setEditedGcode(code.gcode)
    setIsViewOpen(true)
  }

  const handleEditFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const validExtensions = ['.txt', '.gcode', '.gc', '.nc']
    const hasValidExt = validExtensions.some(ext => 
      file.name.toLowerCase().endsWith(ext)
    )
    if (!hasValidExt) {
      toast.error('Please select a valid G-code file (.txt, .gcode, .gc, .nc)')
      return
    }

    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target?.result as string
      setEditedGcode(content)
      toast.success(`Loaded G-code from ${file.name}`)
    }
    reader.onerror = () => {
      toast.error('Failed to read file')
    }
    reader.readAsText(file)
  }

  const handleSave = async () => {
    if (!viewingCode) return
    
    if (!editedName.trim()) {
      toast.error('Please enter a name')
      return
    }
    if (!editedGcode.trim()) {
      toast.error('Please enter the G-code content')
      return
    }

    try {
      await updateCode.mutateAsync({
        id: viewingCode.id,
        data: {
          name: editedName.trim(),
          gcode: editedGcode.trim()
        }
      })
      toast.success(`Ejection code "${editedName}" updated`)
      setIsViewOpen(false)
    } catch {
      toast.error('Failed to update ejection code')
    }
  }

  const hasChanges = viewingCode && (
    editedName !== viewingCode.name || 
    editedGcode !== viewingCode.gcode
  )

  const handleTest = (code: EjectionCode) => {
    setTestingCode(code)
    setSelectedPrinter('')
    setIsTestOpen(true)
  }

  const handleRunTest = async () => {
    if (!testingCode || !selectedPrinter) {
      toast.error('Please select a printer')
      return
    }

    try {
      await testCode.mutateAsync({
        codeId: testingCode.id,
        printerName: selectedPrinter
      })
      toast.success(`Ejection code "${testingCode.name}" sent to ${selectedPrinter}`)
      setIsTestOpen(false)
      setTestingCode(null)
      setSelectedPrinter('')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to send ejection code')
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg">Ejection Codes</CardTitle>
            <CardDescription>
              Saved G-code presets for auto-ejection after prints
            </CardDescription>
          </div>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-1" />
                New
              </Button>
            </DialogTrigger>
            <DialogContent className="w-[90vw] max-w-6xl max-h-[90vh]">
              <DialogHeader>
                <DialogTitle>Create Ejection Code</DialogTitle>
                <DialogDescription>
                  Upload a G-code file or enter the code manually
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="code-name">Name</Label>
                  <Input
                    id="code-name"
                    placeholder="e.g., Front Ejection, Side Wipe"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>G-code Content</Label>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <Upload className="h-4 w-4 mr-1" />
                        Upload File
                      </Button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".txt,.gcode,.gc,.nc"
                        onChange={handleFileUpload}
                        className="hidden"
                      />
                    </div>
                  </div>
                  <GcodeEditor
                    value={newGcode}
                    onChange={setNewGcode}
                    placeholder="; Ejection sequence&#10;G28 X Y&#10;M84"
                  />
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Cancel
                </Button>
                <Button 
                  onClick={handleCreate}
                  disabled={createCode.isPending}
                >
                  {createCode.isPending ? 'Creating...' : 'Create'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : !ejectionCodes || ejectionCodes.length === 0 ? (
          <div className="text-center py-6 text-muted-foreground">
            <Code className="h-10 w-10 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No ejection codes saved yet</p>
            <p className="text-xs mt-1">Create one to quickly select it when adding orders</p>
          </div>
        ) : (
          <div className="space-y-2">
            {ejectionCodes.map((code) => (
              <div
                key={code.id}
                className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <FileCode className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-sm">{code.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {code.gcode.split('\n').length} lines • 
                      Created {new Date(code.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleTest(code)}
                    title="Test on printer"
                  >
                    <Play className="h-4 w-4 text-green-600" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleView(code)}
                    title="View code"
                  >
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(code)}
                    disabled={deleteCode.isPending}
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {/* View/Edit Dialog */}
      <Dialog open={isViewOpen} onOpenChange={setIsViewOpen}>
        <DialogContent className="w-[90vw] max-w-6xl h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Edit Ejection Code</DialogTitle>
            <DialogDescription>
              {viewingCode?.source_filename && `Originally uploaded from ${viewingCode.source_filename}`}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 flex-1 overflow-hidden flex flex-col">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Name</Label>
              <Input
                id="edit-name"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                placeholder="Ejection code name"
              />
            </div>
            
            <div className="space-y-2 flex-1 flex flex-col min-h-0">
              <div className="flex items-center justify-between">
                <Label>G-code Content</Label>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => editFileInputRef.current?.click()}
                  >
                    <Upload className="h-4 w-4 mr-1" />
                    Upload File
                  </Button>
                  <input
                    ref={editFileInputRef}
                    type="file"
                    accept=".txt,.gcode,.gc,.nc"
                    onChange={handleEditFileUpload}
                    className="hidden"
                  />
                </div>
              </div>
              <GcodeEditor
                value={editedGcode}
                onChange={setEditedGcode}
                placeholder="; Ejection sequence&#10;G28 X Y&#10;M84"
              />
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setIsViewOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleSave}
              disabled={updateCode.isPending || !hasChanges}
            >
              {updateCode.isPending ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Test Dialog */}
      <Dialog open={isTestOpen} onOpenChange={setIsTestOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Test Ejection Code</DialogTitle>
            <DialogDescription>
              Send "{testingCode?.name}" to a printer to test the ejection sequence
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="test-printer">Select Printer</Label>
              {availablePrinters.length > 0 ? (
                <Select value={selectedPrinter} onValueChange={setSelectedPrinter}>
                  <SelectTrigger id="test-printer">
                    <SelectValue placeholder="Choose a printer..." />
                  </SelectTrigger>
                  <SelectContent>
                    {availablePrinters.map((printer) => (
                      <SelectItem key={printer.name} value={printer.name}>
                        {printer.name} ({printer.type}) - {printer.status}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <p className="text-sm text-muted-foreground py-2">
                  No printers available for testing. Printers must be in IDLE, READY, or FINISHED state.
                </p>
              )}
            </div>

            <div className="rounded-md bg-muted p-3">
              <p className="text-xs text-muted-foreground mb-2">G-code preview:</p>
              <pre className="text-xs font-mono max-h-32 overflow-auto whitespace-pre-wrap">
                {testingCode?.gcode?.slice(0, 500)}
                {(testingCode?.gcode?.length || 0) > 500 && '...'}
              </pre>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsTestOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleRunTest}
              disabled={!selectedPrinter || testCode.isPending}
            >
              {testCode.isPending ? 'Sending...' : 'Run Test'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

export default EjectionCodesManager
