export function Footer() {
  return (
    <footer className="border-t bg-card mt-auto">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <img src="/logo192.png" alt="PrintQue" className="h-5 w-auto opacity-60" />
            <span>PrintQue - Print Queue Management</span>
          </div>
          <div className="flex items-center gap-4">
            <span>3D Print Farm Automation</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
