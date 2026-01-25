import { createFileRoute } from '@tanstack/react-router'
import { CheckCircle, Github, Heart, Loader2, Printer, Shield } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useLicense } from '@/hooks'

export const Route = createFileRoute('/license')({ component: LicensePage })

function LicensePage() {
  const { data: license, isLoading } = useLicense()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">License</h1>
        <p className="text-muted-foreground">PrintQue Open Source Edition</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              License Status
            </CardTitle>
            <CardDescription>Open source software - all features enabled</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Status</span>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-green-500 font-medium">Active</span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Edition</span>
              <Badge className="bg-green-600">{license?.tier || 'Open Source'}</Badge>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Max Printers</span>
              <span className="font-medium">Unlimited</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">License</span>
              <span className="font-medium">GPL v3</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Printer className="h-5 w-5" />
              Features
            </CardTitle>
            <CardDescription>All features included - no restrictions</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Unlimited printers</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Unlimited library items</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Real-time printer monitoring</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Auto-ejection support</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Printer groups</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>API access</span>
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span>Community support</span>
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Heart className="h-5 w-5 text-red-500" />
            Support the Project
          </CardTitle>
          <CardDescription>PrintQue is free and open source software</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <p className="text-muted-foreground">
              PrintQue is developed and maintained by the community. If you find it useful, consider
              supporting the project:
            </p>
            <div className="flex flex-wrap gap-4">
              <a
                href="https://github.com/PrintQue/PrintQue"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                <Github className="h-4 w-4" />
                Star on GitHub
              </a>
              <a
                href="https://github.com/PrintQue/PrintQue/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                Report Issues
              </a>
              <a
                href="https://github.com/PrintQue/PrintQue/blob/main/CONTRIBUTING.md"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                Contribute
              </a>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
