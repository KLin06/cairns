import { useTheme } from '../theme/useTheme'

export default function ThemeToggle() {
  const { mode, toggle } = useTheme()

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={mode === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
      className="rounded-full border border-(--color-border) px-4 py-2 text-left text-sm text-(--color-base-content) hover:bg-(--color-base-200)"
    >
      {mode === 'light' ? 'Dark mode' : 'Light mode'}
    </button>
  )
}
