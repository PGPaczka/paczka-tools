import { writable } from 'svelte/store'

export interface ViewportState {
  tx: number
  ty: number
  scale: number
  vw: number
  vh: number
}

/**
 * Positions map updated on every simulation tick.
 * Used by Minimap to draw node positions without prop-drilling.
 */
export const minimapPositions = writable<Map<string, { x: number; y: number }>>(new Map())

/**
 * Viewport state updated on every canvas render frame.
 * Used by Minimap to draw the viewport rectangle overlay.
 */
export const minimapViewport = writable<ViewportState>({
  tx: 0,
  ty: 0,
  scale: 1,
  vw: 800,
  vh: 600,
})
