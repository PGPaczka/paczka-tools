import { writable } from 'svelte/store'
import type { LayoutId } from '../layout/layoutRegistry'

export interface Settings {
  layout: LayoutId
  repulsion: number
  linkDist: number
  minimapOn: boolean
  catColorOverrides: Record<string, string>
  /** Color priority for node rendering: 'category' fills nodes, 'status' fills; opposite is the stroke */
  colorPriority: 'category' | 'status'
  /** When false, the secondary colour ring (status/category stroke) is hidden */
  secondaryColorEnabled: boolean
}

const STORAGE_KEY = 'synapse:settings'
const SETTINGS_VERSION = 2

function loadFromStorage(): Settings {
  const defaults: Settings = {
    layout: 'classic',
    repulsion: 820,
    linkDist: 80,
    minimapOn: true,
    catColorOverrides: {},
    colorPriority: 'category',
    secondaryColorEnabled: true,
  }
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<Settings> & { _v?: number }
      // Migrate old settings (version < 2 had repulsion=3000)
      if (!parsed._v || parsed._v < SETTINGS_VERSION) {
        return defaults
      }
      return { ...defaults, ...parsed }
    }
  } catch {
    // localStorage unavailable or parse error
  }
  return defaults
}

export const settings = writable<Settings>(loadFromStorage())

// Persist every change to localStorage
settings.subscribe((value) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...value, _v: SETTINGS_VERSION }))
  } catch {
    // ignore
  }
})
