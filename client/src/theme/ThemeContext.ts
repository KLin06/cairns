import { createContext } from 'react'

export type ThemeMode = 'light' | 'dark'

export interface ThemeContextValue {
  mode: ThemeMode
  toggle: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)
