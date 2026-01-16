import { createFileRoute } from '@tanstack/react-router'
import { useLicense } from '@/hooks'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Loader2, Shield, CheckCircle, XCircle, Printer, Calendar } from 'lucide-react'

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

  const tierColors: Record<string, string> = {
    free: 'bg-gray-500',
    basic: 'bg-blue-500',
    pro: 'bg-purple-500',
    enterprise: 'bg-yellow-500',
  }

  const tierLabels: Record<string, string> = {
    free: 'Free',
    basic: 'Basic',
    pro: 'Professional',
    enterprise: 'Enterprise',
  }

  const tierLimits: Record<string, number> = {
    free: 2,
    basic: 5,
    pro: 20,
    enterprise: 999,
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">License</h1>
        <p className="text-muted-foreground">
          Manage your PrintQue license
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              License Status
            </CardTitle>
            <CardDescription>
              Your current license information
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Status</span>
              <div className="flex items-center gap-2">
                {license?.valid ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="text-green-500 font-medium">Active</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-4 w-4 text-red-500" />
                    <span className="text-red-500 font-medium">Invalid</span>
                  </>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Tier</span>
              <Badge className={tierColors[license?.tier || 'free']}>
                {tierLabels[license?.tier || 'free']}
              </Badge>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Max Printers</span>
              <span className="font-medium">
                {license?.max_printers || tierLimits[license?.tier || 'free']}
              </span>
            </div>

            {license?.expires_at && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Expires</span>
                <span className="font-medium">
                  {new Date(license.expires_at).toLocaleDateString()}
                </span>
              </div>
            )}

            {license?.machine_id && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Machine ID</span>
                <code className="text-xs bg-muted px-2 py-1 rounded">
                  {license.machine_id.slice(0, 8)}...
                </code>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Printer className="h-5 w-5" />
              Features
            </CardTitle>
            <CardDescription>
              Features included in your plan
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
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
                {(license?.tier === 'pro' || license?.tier === 'enterprise') ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={(license?.tier === 'pro' || license?.tier === 'enterprise') ? '' : 'text-muted-foreground'}>
                  Printer groups
                </span>
              </li>
              <li className="flex items-center gap-2">
                {license?.tier === 'enterprise' ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={license?.tier === 'enterprise' ? '' : 'text-muted-foreground'}>
                  Priority support
                </span>
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Upgrade Your Plan
          </CardTitle>
          <CardDescription>
            Get more features and printer support
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="border rounded-lg p-4">
              <h3 className="font-semibold">Basic</h3>
              <p className="text-2xl font-bold mt-2">$9<span className="text-sm font-normal">/mo</span></p>
              <ul className="mt-4 space-y-2 text-sm">
                <li>Up to 5 printers</li>
                <li>Email support</li>
              </ul>
              <Button className="w-full mt-4" variant="outline" disabled={license?.tier === 'basic'}>
                {license?.tier === 'basic' ? 'Current Plan' : 'Select'}
              </Button>
            </div>
            <div className="border rounded-lg p-4 border-primary">
              <h3 className="font-semibold">Professional</h3>
              <p className="text-2xl font-bold mt-2">$29<span className="text-sm font-normal">/mo</span></p>
              <ul className="mt-4 space-y-2 text-sm">
                <li>Up to 20 printers</li>
                <li>Printer groups</li>
                <li>Priority email support</li>
              </ul>
              <Button className="w-full mt-4" disabled={license?.tier === 'pro'}>
                {license?.tier === 'pro' ? 'Current Plan' : 'Select'}
              </Button>
            </div>
            <div className="border rounded-lg p-4">
              <h3 className="font-semibold">Enterprise</h3>
              <p className="text-2xl font-bold mt-2">Contact</p>
              <ul className="mt-4 space-y-2 text-sm">
                <li>Unlimited printers</li>
                <li>Dedicated support</li>
                <li>Custom integrations</li>
              </ul>
              <Button className="w-full mt-4" variant="outline" disabled={license?.tier === 'enterprise'}>
                {license?.tier === 'enterprise' ? 'Current Plan' : 'Contact Sales'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
