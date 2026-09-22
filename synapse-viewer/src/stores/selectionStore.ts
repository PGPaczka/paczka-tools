import { writable } from 'svelte/store'

export const selectedId = writable<string | null>(null)
export const hoveredId = writable<string | null>(null)
