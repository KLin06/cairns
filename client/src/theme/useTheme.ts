import { use } from 'react'
import { ThemeContext } from './ThemeContext'

export function useTheme() {
  const ctx = use(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}
