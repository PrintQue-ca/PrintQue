import { useState, useEffect, useCallback } from 'react'

type Theme = 'dark' | 'light'

const THEME_KEY = 'printque-theme'

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>('dark')

  // Initialize theme from localStorage or default to dark
  useEffect(() => {
    const stored = localStorage.getItem(THEME_KEY) as Theme | null
    if (stored === 'light' || stored === 'dark') {
      setThemeState(stored)
    } else {
      // Default to dark mode
      setThemeState('dark')
    }
  }, [])

  // Apply theme class to document
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [theme])

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme)
    localStorage.setItem(THEME_KEY, newTheme)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark')
  }, [theme, setTheme])

  return { theme, setTheme, toggleTheme }
}
