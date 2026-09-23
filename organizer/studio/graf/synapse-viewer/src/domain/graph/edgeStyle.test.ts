import { describe, it, expect } from 'vitest'
import {
  EDGE_STYLES,
  edgeStyle,
  edgeWidth,
  presentEdgeKinds,
  presentNodeTypes,
  nodeTypeScale,
} from './edgeStyle'
import type { GraphEdge } from './GraphModel'

const edge = (kind: string, confidence?: number): GraphEdge => ({
  source: 'a',
  target: 'b',
  linkText: 'b',
  kind,
  ...(confidence === undefined ? {} : { confidence }),
})

describe('edgeStyle', () => {
  it('gives every known kind a visually distinct line', () => {
    const kinds = Object.keys(EDGE_STYLES)
    const signatures = kinds.map((k) => {
      const s = edgeStyle(k)
      return `${s.color}|${s.dash.join(',')}|${s.arrow}`
    })

    expect(new Set(signatures).size).toBe(kinds.length)
  })

  it('falls back to a visible style for a kind this viewer does not know', () => {
    const style = edgeStyle('supersedes')

    expect(style.color).toBeTruthy()
    expect(style.label).toBe('supersedes')
  })

  it('treats a missing kind as a plain wikilink', () => {
    expect(edgeStyle(undefined)).toEqual(EDGE_STYLES.link)
  })

  it('marks only genuinely directed kinds with an arrow', () => {
    expect(edgeStyle('older_version').arrow).toBe(true)
    expect(edgeStyle('belongs_to').arrow).toBe(true)
    expect(edgeStyle('near_duplicate').arrow).toBe(false)
    expect(edgeStyle('link').arrow).toBe(false)
  })
})

describe('edgeWidth', () => {
  it('widens with confidence so a guess does not look like a certainty', () => {
    const weak = edgeWidth(edge('near_duplicate', 0.5))
    const strong = edgeWidth(edge('near_duplicate', 1))

    expect(strong).toBeGreaterThan(weak)
  })

  it('uses the plain style width when the vault declared no confidence', () => {
    expect(edgeWidth(edge('near_duplicate'))).toBe(EDGE_STYLES.near_duplicate.width)
  })

  it('clamps confidence outside 0..1 instead of producing absurd widths', () => {
    expect(edgeWidth(edge('link', 5))).toBe(edgeWidth(edge('link', 1)))
    expect(edgeWidth(edge('link', -3))).toBe(edgeWidth(edge('link', 0)))
  })
})

describe('presentEdgeKinds', () => {
  it('lists only kinds actually in the graph, known ones first', () => {
    const kinds = presentEdgeKinds([
      edge('supersedes'),
      edge('near_duplicate'),
      edge('link'),
      edge('link'),
    ])

    expect(kinds).toEqual(['link', 'near_duplicate', 'supersedes'])
  })
})

describe('presentNodeTypes', () => {
  it('orders a known hierarchy coarsest-first and ignores untyped notes', () => {
    expect(
      presentNodeTypes(['file', undefined, 'semester', null, 'category', 'subject', 'file']),
    ).toEqual([
      'semester',
      'subject',
      'category',
      'file',
    ])
  })

  it('keeps unknown types rather than dropping them', () => {
    expect(presentNodeTypes(['lecture', 'file'])).toEqual(['file', 'lecture'])
  })
})

describe('nodeTypeScale', () => {
  it('makes containers bigger than what they contain', () => {
    expect(nodeTypeScale('semester')).toBeGreaterThan(nodeTypeScale('subject'))
    expect(nodeTypeScale('subject')).toBeGreaterThan(nodeTypeScale('category'))
    expect(nodeTypeScale('category')).toBeGreaterThan(nodeTypeScale('file'))
    expect(nodeTypeScale(undefined)).toBe(nodeTypeScale('file'))
  })
})
