export interface PaletteAction {
  id: string
  label: string
  hint: string
  icon: string // SVG string or icon name
  run: () => void
}

export interface ActionCallbacks {
  switchViewGraph: () => void
  switchViewCards: () => void
  switchViewDash: () => void
  switchLayoutClassic: () => void
  switchLayoutRail: () => void
  switchLayoutCommand: () => void
  openSettings: () => void
}

// Simple SVG icon helpers (single path, 16x16 viewBox)
const ICONS: Record<string, string> = {
  graph: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <circle cx="3" cy="8" r="2"/><circle cx="13" cy="3" r="2"/><circle cx="13" cy="13" r="2"/>
    <line x1="5" y1="7.2" x2="11" y2="4" stroke="currentColor" stroke-width="1.5"/>
    <line x1="5" y1="8.8" x2="11" y2="12" stroke="currentColor" stroke-width="1.5"/>
  </svg>`,
  cards: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>
    <rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/>
  </svg>`,
  dash: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="14" height="4" rx="1"/>
    <rect x="1" y="7" width="6" height="8" rx="1"/>
    <rect x="9" y="7" width="6" height="8" rx="1"/>
  </svg>`,
  classic: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="14" height="3" rx="1"/>
    <rect x="1" y="6" width="14" height="9" rx="1" fill-opacity=".4"/>
  </svg>`,
  rail: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="3" height="14" rx="1"/>
    <rect x="6" y="1" width="9" height="14" rx="1" fill-opacity=".4"/>
  </svg>`,
  command: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="3" y="1" width="10" height="3" rx="1.5"/>
    <rect x="1" y="6" width="14" height="9" rx="1" fill-opacity=".4"/>
  </svg>`,
  settings: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M6.5 1h3l.5 2a5 5 0 011.2.7l2-.7 1.5 2.6-1.6 1.3a5 5 0 010 1.8l1.6 1.3-1.5 2.6-2-.7A5 5 0 0110 13.3l-.5 1.7h-3l-.5-1.7A5 5 0 015 12.6l-2 .7L1.5 10.7l1.6-1.3a5 5 0 010-1.8L1.5 6.3 3 3.7l2 .7A5 5 0 016 3.7L6.5 1zM8 10a2 2 0 100-4 2 2 0 000 4z"/>
  </svg>`,
}

export function buildActionsRegistry(callbacks: ActionCallbacks): PaletteAction[] {
  return [
    {
      id: 'switch-view-graph',
      label: 'Graph view',
      hint: 'Show knowledge graph',
      icon: ICONS.graph,
      run: callbacks.switchViewGraph,
    },
    {
      id: 'switch-view-cards',
      label: 'Cards view',
      hint: 'Show notes as cards',
      icon: ICONS.cards,
      run: callbacks.switchViewCards,
    },
    {
      id: 'switch-view-dash',
      label: 'Dashboard',
      hint: 'Show dashboard stats',
      icon: ICONS.dash,
      run: callbacks.switchViewDash,
    },
    {
      id: 'switch-layout-classic',
      label: 'Classic layout',
      hint: 'Top bar navigation',
      icon: ICONS.classic,
      run: callbacks.switchLayoutClassic,
    },
    {
      id: 'switch-layout-rail',
      label: 'Rail layout',
      hint: 'Side icon rail navigation',
      icon: ICONS.rail,
      run: callbacks.switchLayoutRail,
    },
    {
      id: 'switch-layout-command',
      label: 'Command layout',
      hint: 'Floating command bar',
      icon: ICONS.command,
      run: callbacks.switchLayoutCommand,
    },
    {
      id: 'open-settings',
      label: 'Settings',
      hint: 'Open settings panel',
      icon: ICONS.settings,
      run: callbacks.openSettings,
    },
  ]
}
