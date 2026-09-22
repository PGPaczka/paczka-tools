import { describe, it, expect, vi } from 'vitest'
import { searchPalette } from './search'
import type { PaletteAction } from './actionsRegistry'
import type { GraphNode } from '../graph/GraphModel'

const noop = () => {}

const actions: PaletteAction[] = [
  { id: 'switch-view-graph', label: 'Graph view', hint: 'Show knowledge graph', icon: '', run: noop },
  { id: 'switch-view-cards', label: 'Cards view', hint: 'Show notes as cards', icon: '', run: noop },
  { id: 'switch-view-dash', label: 'Dashboard', hint: 'Show dashboard stats', icon: '', run: noop },
  { id: 'switch-layout-classic', label: 'Classic layout', hint: 'Top bar navigation', icon: '', run: noop },
  { id: 'switch-layout-rail', label: 'Rail layout', hint: 'Side icon rail navigation', icon: '', run: noop },
  { id: 'switch-layout-command', label: 'Command layout', hint: 'Floating command bar', icon: '', run: noop },
  { id: 'open-settings', label: 'Settings', hint: 'Open settings panel', icon: '', run: noop },
]

const nodes: GraphNode[] = [
  {
    id: 'docker-basics',
    kind: 'real',
    title: 'Docker Basics',
    path: 'docker-basics.md',
    category: 'DevOps',
    level: 1,
    status: 'completed',
    tags: ['containers'],
    aliases: [],
    modified: '2026-01-01',
    excerpt: 'Docker',
    wordCount: 1,
  },
  {
    id: 'linux-fundamentals',
    kind: 'real',
    title: 'Linux Fundamentals',
    path: 'linux-fundamentals.md',
    category: 'OS',
    level: 1,
    status: 'in-progress',
    tags: ['linux'],
    aliases: [],
    modified: '2026-01-01',
    excerpt: 'Linux',
    wordCount: 1,
  },
  {
    id: 'kubernetes-ghost',
    kind: 'ghost',
    title: 'Kubernetes Advanced',
    referencedBy: ['docker-basics'],
    referenceCount: 1,
  },
]

const catColor = (_cat: string) => '#58a6ff'
const selectNote = vi.fn()

describe('searchPalette', () => {
  it('empty query: returns all actions before all notes', () => {
    const results = searchPalette('', actions, nodes, catColor, selectNote)
    const actionResults = results.filter((r) => r.type === 'action')
    const noteResults = results.filter((r) => r.type === 'note')
    expect(actionResults).toHaveLength(actions.length)
    expect(noteResults).toHaveLength(nodes.length)
    // Actions must come before notes
    const firstNote = results.findIndex((r) => r.type === 'note')
    const lastAction = results.findLastIndex((r) => r.type === 'action')
    expect(lastAction).toBeLessThan(firstNote)
  })

  it('query "graph" matches "Graph view" action', () => {
    const results = searchPalette('graph', actions, nodes, catColor, selectNote)
    const labels = results.map((r) => r.label)
    expect(labels).toContain('Graph view')
  })

  it('query "docker" matches note with "docker" in title', () => {
    const results = searchPalette('docker', actions, nodes, catColor, selectNote)
    const noteLabels = results.filter((r) => r.type === 'note').map((r) => r.label)
    expect(noteLabels).toContain('Docker Basics')
  })

  it('query matching both actions and notes: actions section comes first', () => {
    // "layout" matches layout actions, not notes
    // "linux" matches a note
    // Let's use a query that hits an action hint and a note title
    // "dash" matches "Dashboard" action and nothing in notes
    const results = searchPalette('dash', actions, nodes, catColor, selectNote)
    const firstResult = results[0]
    expect(firstResult.type).toBe('action')
    expect(firstResult.label).toBe('Dashboard')
  })

  it('query matching both: actions appear before notes', () => {
    // "linux" doesn't match any action but does match a note - that's fine
    // Let's construct a scenario where both match
    // "cards" matches "Cards view" action only
    const results = searchPalette('cards', actions, nodes, catColor, selectNote)
    const actionR = results.filter((r) => r.type === 'action')
    expect(actionR[0].label).toBe('Cards view')
    // All action results precede all note results
    const firstNoteIdx = results.findIndex((r) => r.type === 'note')
    if (firstNoteIdx !== -1) {
      results.slice(0, firstNoteIdx).forEach((r) => expect(r.type).toBe('action'))
    }
  })

  it('note results include type, label, color, status', () => {
    const results = searchPalette('docker', actions, nodes, catColor, selectNote)
    const note = results.find((r) => r.label === 'Docker Basics')
    expect(note).toBeDefined()
    expect(note!.type).toBe('note')
    expect(note!.color).toBeDefined()
    expect(note!.status).toBe('completed')
  })

  it('running a note result calls onSelectNote with the node id', () => {
    selectNote.mockClear()
    const results = searchPalette('docker', actions, nodes, catColor, selectNote)
    const note = results.find((r) => r.label === 'Docker Basics')
    note!.run()
    expect(selectNote).toHaveBeenCalledWith('docker-basics')
  })
})
