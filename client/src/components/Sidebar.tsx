import type { ReactNode } from 'react'
import ThemeToggle from './ThemeToggle'

export type SidebarView = 'explore' | 'saved'

interface SidebarSection {
  id: SidebarView | 'plans'
  label: string
  enabled: boolean
  icon: ReactNode
}

const ICON_PROPS = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

// FR-001: Explore and Saved are both functional/navigable; the previously-
// separate Favorited entry is gone (spec 006 consolidates it into Saved).
// Plans remains an existing disabled placeholder, unaffected.
const SECTIONS: SidebarSection[] = [
  {
    id: 'explore',
    label: 'Explore',
    enabled: true,
    icon: (
      <svg {...ICON_PROPS}>
        <polygon points="3 11 22 2 13 21 11 13 3 11" />
      </svg>
    ),
  },
  {
    id: 'saved',
    label: 'Saved',
    enabled: true,
    icon: (
      <svg {...ICON_PROPS}>
        <path d="M19 21 12 16l-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    id: 'plans',
    label: 'Plans',
    enabled: false,
    icon: (
      <svg {...ICON_PROPS}>
        <rect x="3" y="4" width="18" height="18" rx="2" />
        <path d="M3 10h18M8 2v4M16 2v4" />
      </svg>
    ),
  },
]

interface SidebarProps {
  activeView: SidebarView
  onSelect: (view: SidebarView) => void
}

export default function Sidebar({ activeView, onSelect }: SidebarProps) {
  return (
    <nav aria-label="Main" className="flex w-56 flex-col border-r border-(--color-border) bg-(--color-base-100)">
      <div className="border-b border-(--color-border) px-4 py-4">
        <span className="text-lg font-bold tracking-tight text-(--color-accent)">Cairns</span>
      </div>

      <div className="flex flex-col">
        {SECTIONS.map((section) => {
          const isActive = section.id === activeView
          return (
            <button
              key={section.id}
              type="button"
              disabled={!section.enabled}
              aria-current={isActive ? 'page' : undefined}
              onClick={section.enabled ? () => onSelect(section.id as SidebarView) : undefined}
              className={
                'flex items-center gap-3 border-b border-l-4 border-(--color-border) px-4 py-3 text-left text-sm ' +
                (isActive
                  ? 'border-l-(--color-accent) bg-(--color-base-200) font-medium text-(--color-accent)'
                  : section.enabled
                    ? 'border-l-transparent text-(--color-base-content) hover:bg-(--color-base-200)'
                    : 'cursor-not-allowed border-l-transparent text-(--color-neutral-content) opacity-50')
              }
            >
              {section.icon}
              {section.label}
            </button>
          )
        })}
      </div>

      <div className="mt-auto border-t border-(--color-border) p-3">
        <ThemeToggle />
      </div>
    </nav>
  )
}
