export type LayoutId = 'classic' | 'rail' | 'command'

export interface LayoutEntry {
  id: LayoutId
  label: string
}

export const layouts: LayoutEntry[] = [
  { id: 'classic', label: 'Classic · top bar' },
  { id: 'rail', label: 'Rail · side nav' },
  { id: 'command', label: 'Command · floating bar' },
]
