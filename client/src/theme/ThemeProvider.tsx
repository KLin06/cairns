import { useEffect, useState, type ReactNode } from 'react'
import { ThemeContext, type ThemeMode } from './ThemeContext'

const STORAGE_KEY = 'cairns-theme'

function readStoredMode(): ThemeMode {
  // FR-020: default to light when nothing is stored yet.
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'dark' ? 'dark' : 'light'
}

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readStoredMode)

  useEffect(() => {
    document.documentElement.dataset.theme = mode === 'dark' ? 'cairns-dark' : 'cairns-light'
    localStorage.setItem(STORAGE_KEY, mode) // FR-021: persist across reloads
  }, [mode])

  const toggle = () => setMode((prev) => (prev === 'light' ? 'dark' : 'light'))

  return <ThemeContext value={{ mode, toggle }}>{children}</ThemeContext>
}
