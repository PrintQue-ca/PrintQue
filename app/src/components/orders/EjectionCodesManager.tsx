import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog'
import { Upload, Plus, FileCode, Trash2, Code, Edit2 } from 'lucide-react'
import { 
  useEjectionCodes, 
  useCreateEjectionCode, 
  useUploadEjectionCode, 
  useDeleteEjectionCode 
} from '@/hooks'
import { toast } from 'sonner'
import type { EjectionCode } from '@/types'

export function EjectionCodesManager() {
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [isViewOpen, setIsViewOpen] = useState(false)
  const [viewingCode, setViewingCode] = useState<EjectionCode | null>(null)
  const [newName, setNewName] = useState('')
  const [newGcode, setNewGcode] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const { data: ejectionCodes, isLoading } = useEjectionCodes()
  const createCode = useCreateEjectionCode()
  const uploadCode = useUploadEjectionCode()
  const deleteCode = useDeleteEjectionCode()

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
    setIsViewOpen(true)
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
            <DialogContent className="max-w-lg">
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
                  <Label>G-code Content</Label>
                  <div className="flex gap-2 mb-2">
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
                  <Textarea
                    value={newGcode}
                    onChange={(e) => setNewGcode(e.target.value)}
                    placeholder="; Ejection sequence&#10;G28 X Y&#10;M84"
                    rows={8}
                    className="font-mono text-xs"
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{viewingCode?.name}</DialogTitle>
            <DialogDescription>
              {viewingCode?.source_filename && `Uploaded from ${viewingCode.source_filename}`}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-2">
            <Label>G-code Content</Label>
            <Textarea
              value={viewingCode?.gcode || ''}
              readOnly
              rows={12}
              className="font-mono text-xs"
            />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsViewOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

export default EjectionCodesManager
