import { TanStackDevtools } from '@tanstack/react-devtools'
import type { QueryClient } from '@tanstack/react-query'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import {
  createRootRouteWithContext,
  HeadContent,
  Link,
  Outlet,
  Scripts,
} from '@tanstack/react-router'
import { TanStackRouterDevtoolsPanel } from '@tanstack/react-router-devtools'
import { useEffect } from 'react'
import { Toaster } from 'sonner'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/hooks'
import { initSocket } from '@/lib/socket'
import { queryClient } from '@/router'
import appCss from '../styles.css?url'

function NotFound() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
      <h1 className="text-4xl font-bold">404</h1>
      <p className="text-muted-foreground">Page not found</p>
      <Link to="/" className="text-primary hover:underline">
        Go back to Dashboard
      </Link>
    </div>
  )
}

export const Route = createRootRouteWithContext<{
  queryClient: QueryClient
}>()({
  notFoundComponent: NotFound,
  head: () => ({
    meta: [
      {
        charSet: 'utf-8',
      },
      {
        name: 'viewport',
        content: 'width=device-width, initial-scale=1',
      },
      {
        title: 'PrintQue - Print Queue Management',
      },
    ],
    links: [
      {
        rel: 'stylesheet',
        href: appCss,
      },
      {
        rel: 'icon',
        href: '/favicon.ico',
      },
      {
        rel: 'apple-touch-icon',
        href: '/apple-touch-icon.png',
      },
    ],
  }),

  component: RootComponent,
})

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      className="h-9 w-9"
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      {theme === 'dark' ? (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-5 w-5"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2" />
          <path d="M12 20v2" />
          <path d="m4.93 4.93 1.41 1.41" />
          <path d="m17.66 17.66 1.41 1.41" />
          <path d="M2 12h2" />
          <path d="M20 12h2" />
          <path d="m6.34 17.66-1.41 1.41" />
          <path d="m19.07 4.93-1.41 1.41" />
        </svg>
      ) : (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-5 w-5"
        >
          <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
        </svg>
      )}
    </Button>
  )
}

function Navigation() {
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
              <Link
                to="/"
                className="text-sm font-medium transition-colors hover:text-primary [&.active]:text-primary [&.active]:font-semibold"
                activeOptions={{ exact: true }}
              >
                Dashboard
              </Link>
              <Link
                to="/printers"
                className="text-sm font-medium transition-colors hover:text-primary [&.active]:text-primary [&.active]:font-semibold"
              >
                Printers
              </Link>
              <Link
                to="/stats"
                className="text-sm font-medium transition-colors hover:text-primary [&.active]:text-primary [&.active]:font-semibold"
              >
                Stats
              </Link>
              <Link
                to="/license"
                className="text-sm font-medium transition-colors hover:text-primary [&.active]:text-primary [&.active]:font-semibold"
              >
                License
              </Link>
              <Link
                to="/system"
                className="text-sm font-medium transition-colors hover:text-primary [&.active]:text-primary [&.active]:font-semibold"
              >
                System
              </Link>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </div>
    </nav>
  )
}

function Footer() {
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

function RootComponent() {
  const { theme } = useTheme()

  // Initialize socket connection when app loads
  useEffect(() => {
    initSocket(queryClient)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <RootDocument>
        <div className="flex flex-col min-h-screen">
          <Navigation />
          <main className="container mx-auto p-4 flex-1">
            <Outlet />
          </main>
          <Footer />
        </div>
        <Toaster position="bottom-right" theme={theme} />
      </RootDocument>
      <ReactQueryDevtools buttonPosition="bottom-left" />
    </QueryClientProvider>
  )
}

// Script to prevent flash of wrong theme on initial load
const themeScript = `
  (function() {
    const stored = localStorage.getItem('printque-theme');
    const theme = stored === 'light' ? 'light' : 'dark';
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    }
  })();
`

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-screen bg-background text-foreground">
        {children}
        <TanStackDevtools
          config={{
            position: 'bottom-right',
          }}
          plugins={[
            {
              name: 'Tanstack Router',
              render: <TanStackRouterDevtoolsPanel />,
            },
          ]}
        />
        <Scripts />
      </body>
    </html>
  )
}
