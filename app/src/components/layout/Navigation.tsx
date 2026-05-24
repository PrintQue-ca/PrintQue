import { Link } from '@tanstack/react-router'
import { CommunityNavLinks } from '@/components/layout/CommunityNavLinks'
import { ConnectionBanner } from '@/components/layout/ConnectionBanner'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { listSearchDefaults } from '@/lib/list-search-params'

const navLinkClass =
  'text-sm font-medium transition-colors hover:text-primary [&.active]:text-primary [&.active]:font-semibold'

export function Navigation() {
  return (
    <nav className="border-b bg-card">
      <div className="h-1 bg-linear-to-r from-primary via-primary/80 to-primary/60" />
      <div className="container mx-auto px-4">
        <div className="flex h-14 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center hover:opacity-80 transition-opacity">
              <img src="/logo192.png" alt="PrintQue" className="h-8 w-auto" />
            </Link>
            <div className="flex items-center gap-4">
              <Link to="/" className={navLinkClass} activeOptions={{ exact: true }}>
                Dashboard
              </Link>
              <Link to="/library" search={listSearchDefaults} className={navLinkClass}>
                Library
              </Link>
              <Link to="/orders" search={listSearchDefaults} className={navLinkClass}>
                Orders
              </Link>
              <Link to="/printers" className={navLinkClass}>
                Printers
              </Link>
              <Link to="/stats" className={navLinkClass}>
                Stats
              </Link>
              <Link to="/ejection-codes" className={navLinkClass}>
                Ejection Codes
              </Link>
              <Link to="/system" className={navLinkClass}>
                System
              </Link>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <CommunityNavLinks />
            <ConnectionBanner />
            <ThemeToggle />
          </div>
        </div>
      </div>
    </nav>
  )
}
