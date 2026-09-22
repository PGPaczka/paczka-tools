import { describe, it, expect, beforeEach, vi } from 'vitest'
import { categoryColor } from './categoryColor'

describe('categoryColor', () => {
  it('same string always returns the same color (deterministic)', () => {
    expect(categoryColor('DevOps')).toBe(categoryColor('DevOps'))
    expect(categoryColor('OS')).toBe(categoryColor('OS'))
  })

  it('different strings return different colors', () => {
    // With high probability djb2 distinguishes these
    expect(categoryColor('DevOps')).not.toBe(categoryColor('OS'))
  })

  it('user override takes precedence over hash fallback', () => {
    const overrides = { DevOps: '#ff0000' }
    expect(categoryColor('DevOps', overrides)).toBe('#ff0000')
  })

  it('override for one category does not affect another', () => {
    const overrides = { DevOps: '#ff0000' }
    const osColor = categoryColor('OS')
    expect(categoryColor('OS', overrides)).toBe(osColor)
  })

  it('returns a valid #rrggbb hex string for any input', () => {
    const color = categoryColor('SomeRandomCategory')
    expect(color).toMatch(/^#[0-9a-f]{6}$/)
  })
})

describe('categoryColor with localStorage overrides', () => {
  beforeEach(() => {
    // jsdom provides localStorage; clear it before each test
    localStorage.clear()
  })

  it('getUserOverrides returns empty object when nothing stored', async () => {
    const { getUserOverrides } = await import('./categoryColor')
    expect(getUserOverrides()).toEqual({})
  })

  it('setUserOverride persists and getUserOverrides reads back', async () => {
    const { getUserOverrides, setUserOverride } = await import('./categoryColor')
    setUserOverride('Tools', '#aabbcc')
    expect(getUserOverrides()['Tools']).toBe('#aabbcc')
  })
})
