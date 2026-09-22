import { writable } from 'svelte/store'

/**
 * Increment this to trigger a fitToNodes() call in the active GraphCanvas.
 * Any component can fire the fit by calling `fitTrigger.update(n => n + 1)`.
 */
export const fitTrigger = writable(0)
