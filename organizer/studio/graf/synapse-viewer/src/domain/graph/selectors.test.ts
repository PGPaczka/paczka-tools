import { describe, it, expect } from 'vitest'
import {
  visibleNodes,
  visibleEdges,
  orphanIds,
  backlinks,
  outgoing,
  defaultFiltersFor,
  LARGE_VAULT_NODES,
} from './selectors'
import type { KnowledgeGraph } from './GraphModel'

/**
 * Mini-graph for selector tests:
 *
 * Nodes:
 *   docker-basics    (real, DevOps, level 1, completed)
 *   linux-fundamentals (real, OS, level 1, completed)
 *   vim-shortcuts    (real, Tools, level 1, completed)  ← ORPHAN (no edges)
 *   docker-volumes   (real, DevOps, level 2, not-started)
 *   kubernetes advanced (ghost)
 *
 * Edges:
 *   docker-basics → linux-fundamentals
 *   docker-volumes → kubernetes advanced
 */
const miniGraph: KnowledgeGraph = {
  schemaVersion: 2,
  generatedAt: '2026-01-01T00:00:00Z',
  vault: { name: 'Test', notesCount: 4, ghostCount: 1, orphanCount: 1 },
  nodes: [
    {
      id: 'docker-basics',
      kind: 'real',
      title: 'Docker Basics',
      path: 'docker-basics.md',
      category: 'DevOps',
      level: 1,
      status: 'completed',
      tags: ['containers', 'cli'],
      aliases: [],
      modified: '2026-03-10',
      excerpt: 'Docker basics',
      wordCount: 2,
    },
    {
      id: 'linux-fundamentals',
      kind: 'real',
      title: 'Linux Fundamentals',
      path: 'linux-fundamentals.md',
      category: 'OS',
      level: 1,
      status: 'completed',
      tags: ['linux', 'cli'],
      aliases: [],
      modified: '2026-03-01',
      excerpt: 'Linux basics',
      wordCount: 2,
    },
    {
      id: 'vim-shortcuts',
      kind: 'real',
      title: 'Vim Shortcuts',
      path: 'vim-shortcuts.md',
      category: 'Tools',
      level: 1,
      status: 'completed',
      tags: ['cli', 'editor'],
      aliases: [],
      modified: '2026-04-15',
      excerpt: 'Vim tips',
      wordCount: 2,
    },
    {
      id: 'docker-volumes',
      kind: 'real',
      title: 'Docker Volumes',
      path: 'docker-volumes.md',
      category: 'DevOps',
      level: 2,
      status: 'not-started',
      tags: ['containers', 'storage'],
      aliases: [],
      modified: '2026-06-10',
      excerpt: 'Volumes',
      wordCount: 1,
    },
    {
      id: 'kubernetes advanced',
      kind: 'ghost',
      title: 'Kubernetes Advanced',
      referencedBy: ['docker-volumes'],
      referenceCount: 1,
    },
  ],
  edges: [
    {
      source: 'docker-basics',
      target: 'linux-fundamentals',
      linkText: '[[linux-fundamentals]]',
      kind: 'link',
    },
    {
      source: 'docker-volumes',
      target: 'kubernetes advanced',
      linkText: '[[Kubernetes Advanced]]',
      kind: 'link',
    },
  ],
}

describe('orphanIds', () => {
  it('identifies vim-shortcuts as the only orphan', () => {
    const orphans = orphanIds(miniGraph)
    expect(orphans.has('vim-shortcuts')).toBe(true)
    expect(orphans.size).toBe(1)
  })
})

describe('backlinks', () => {
  it('returns edges where target === id', () => {
    const bl = backlinks(miniGraph, 'linux-fundamentals')
    expect(bl).toHaveLength(1)
    expect(bl[0].source).toBe('docker-basics')
    expect(bl[0].target).toBe('linux-fundamentals')
  })

  it('returns empty array for a node with no incoming edges', () => {
    expect(backlinks(miniGraph, 'docker-basics')).toHaveLength(0)
  })
})

describe('outgoing', () => {
  it('returns edges where source === id', () => {
    const out = outgoing(miniGraph, 'docker-basics')
    expect(out).toHaveLength(1)
    expect(out[0].target).toBe('linux-fundamentals')
  })

  it('returns empty array for a node with no outgoing edges', () => {
    expect(outgoing(miniGraph, 'vim-shortcuts')).toHaveLength(0)
  })
})

describe('visibleNodes', () => {
  const emptyFilters = { categories: [], statuses: [], levels: [], tags: [], nodeTypes: [], relationKinds: [] }

  it('returns all nodes when filters are empty', () => {
    const result = visibleNodes(miniGraph, emptyFilters)
    expect(result).toHaveLength(miniGraph.nodes.length)
  })

  it('filters by category, ghost nodes always pass', () => {
    const result = visibleNodes(miniGraph, { ...emptyFilters, categories: ['DevOps'] })
    const ids = result.map((n) => n.id)
    // DevOps real nodes
    expect(ids).toContain('docker-basics')
    expect(ids).toContain('docker-volumes')
    // Ghost always passes
    expect(ids).toContain('kubernetes advanced')
    // OS and Tools nodes excluded
    expect(ids).not.toContain('linux-fundamentals')
    expect(ids).not.toContain('vim-shortcuts')
  })

  it('filters by status', () => {
    const result = visibleNodes(miniGraph, { ...emptyFilters, statuses: ['not-started'] })
    const ids = result.map((n) => n.id)
    expect(ids).toContain('docker-volumes')
    expect(ids).toContain('kubernetes advanced') // ghost passes
    expect(ids).not.toContain('docker-basics') // completed
  })

  it('filters by level', () => {
    const result = visibleNodes(miniGraph, { ...emptyFilters, levels: [2] })
    const ids = result.map((n) => n.id)
    expect(ids).toContain('docker-volumes') // level 2
    expect(ids).toContain('kubernetes advanced') // ghost passes
    expect(ids).not.toContain('docker-basics') // level 1
  })

  it('filters by tag', () => {
    const result = visibleNodes(miniGraph, { ...emptyFilters, tags: ['storage'] })
    const ids = result.map((n) => n.id)
    expect(ids).toContain('docker-volumes') // has 'storage' tag
    expect(ids).toContain('kubernetes advanced') // ghost passes
    expect(ids).not.toContain('docker-basics') // no 'storage' tag
  })
})

describe('visibleNodes — node type', () => {
  const typed: KnowledgeGraph = {
    ...miniGraph,
    nodes: miniGraph.nodes.map((n, i) =>
      n.kind === 'real' ? { ...n, type: i === 0 ? 'subject' : 'file' } : n,
    ),
  }

  it('filters by node type', () => {
    const result = visibleNodes(typed, {
      categories: [], statuses: [], levels: [], tags: [],
      nodeTypes: ['subject'], relationKinds: [],
    })

    // Only the subject: a ghost has no type, so an explicit type filter excludes it.
    expect(result.map((n) => n.id)).toEqual(['docker-basics'])
  })

  it('excludes ghosts when a node type is requested — a ghost has no type', () => {
    const result = visibleNodes(typed, {
      categories: [], statuses: [], levels: [], tags: [],
      nodeTypes: ['file'], relationKinds: [],
    })

    expect(result.every((n) => n.kind === 'real')).toBe(true)
  })

  it('survives a filter object missing the newer dimensions', () => {
    // Older persisted/partial filter state must not blank the graph.
    const partial = { categories: [], statuses: [], levels: [], tags: [] } as never

    expect(visibleNodes(typed, partial)).toHaveLength(typed.nodes.length)
  })
})

describe('visibleEdges', () => {
  const mixed: KnowledgeGraph = {
    ...miniGraph,
    edges: [
      { source: 'docker-basics', target: 'linux-fundamentals', linkText: 'x', kind: 'link' },
      {
        source: 'docker-basics',
        target: 'docker-volumes',
        linkText: 'y',
        kind: 'near_duplicate',
        confidence: 0.8,
      },
    ],
  }

  it('returns every edge when no relation kind is selected', () => {
    expect(
      visibleEdges(mixed, {
        categories: [], statuses: [], levels: [], tags: [], nodeTypes: [], relationKinds: [],
      }),
    ).toHaveLength(2)
  })

  it('hides the connection, not the notes', () => {
    const filters = {
      categories: [], statuses: [], levels: [], tags: [], nodeTypes: [],
      relationKinds: ['near_duplicate'],
    }

    const edges = visibleEdges(mixed, filters)

    expect(edges.map((e) => e.kind)).toEqual(['near_duplicate'])
    // Nodes stay: filtering a relation must not shrink the vault.
    expect(visibleNodes(mixed, filters)).toHaveLength(mixed.nodes.length)
  })
})

describe('defaultFiltersFor', () => {
  function vaultOf(count: number, typed: boolean): KnowledgeGraph {
    return {
      ...miniGraph,
      nodes: Array.from({ length: count }, (_, i) => ({
        id: `n${i}`,
        kind: 'real' as const,
        title: `n${i}`,
        path: `n${i}.md`,
        category: 'X',
        level: 1,
        status: 'completed' as const,
        tags: [],
        aliases: [],
        modified: '2026-01-01',
        excerpt: '',
        wordCount: 0,
        ...(typed ? { type: i % 3 === 0 ? 'subject' : 'file' } : {}),
      })),
    }
  }

  it('does not filter a small vault — seeing everything is the point', () => {
    expect(defaultFiltersFor(vaultOf(50, true)).nodeTypes).toEqual([])
  })

  it('does not filter a large vault that declares no node types', () => {
    expect(defaultFiltersFor(vaultOf(LARGE_VAULT_NODES + 1, false)).nodeTypes).toEqual([])
  })

  it('opens a large typed vault at its coarse level, hiding the most granular type', () => {
    const filters = defaultFiltersFor(vaultOf(LARGE_VAULT_NODES + 1, true))

    expect(filters.nodeTypes).toEqual(['subject'])
    expect(filters.nodeTypes).not.toContain('file')
  })
})

describe('tag mode', () => {
  const tagged: KnowledgeGraph = {
    ...miniGraph,
    nodes: miniGraph.nodes.map((n, i) =>
      n.kind === 'real' ? { ...n, tags: i === 0 ? ['ako', 'do-przegladu'] : ['ako'] } : n,
    ),
  }
  const base = {
    categories: [], statuses: [], levels: [], nodeTypes: [], relationKinds: [],
  }

  it("'all' answers 'this subject AND needs review' — the union cannot", () => {
    const all = visibleNodes(tagged, { ...base, tags: ['ako', 'do-przegladu'], tagMode: 'all' })
    const any = visibleNodes(tagged, { ...base, tags: ['ako', 'do-przegladu'], tagMode: 'any' })

    expect(all.filter((n) => n.kind === 'real').map((n) => n.id)).toEqual(['docker-basics'])
    expect(any.filter((n) => n.kind === 'real').length).toBeGreaterThan(1)
  })

  it('defaults to the union when no mode is given (older filter objects)', () => {
    const result = visibleNodes(tagged, { ...base, tags: ['ako', 'do-przegladu'] })

    expect(result.filter((n) => n.kind === 'real').length).toBeGreaterThan(1)
  })
})

describe('connected-only', () => {
  const base = {
    categories: [], statuses: [], levels: [], tags: [], nodeTypes: [], relationKinds: [],
  }

  it('drops notes with no visible edge, which is what makes a relation filter usable', () => {
    // Ask for one relation kind in a big vault and most notes have nothing to show:
    // they stay on screen as dust and bury the handful that answer the question.
    const ids = visibleNodes(miniGraph, { ...base, connectedOnly: true }).map((n) => n.id)

    expect(ids).not.toContain('vim-shortcuts')
    expect(ids).toContain('docker-basics')
    expect(ids).toContain('linux-fundamentals')
  })

  it('judges connectedness by the edges being DRAWN, not by every edge in the vault', () => {
    const ids = visibleNodes(miniGraph, {
      ...base,
      relationKinds: ['nonexistent-kind'],
      connectedOnly: true,
    }).map((n) => n.id)

    expect(ids).toEqual([])
  })

  it('needs both ends visible — an edge into a filtered-out note does not count', () => {
    const ids = visibleNodes(miniGraph, {
      ...base,
      categories: ['DevOps'],
      connectedOnly: true,
    }).map((n) => n.id)

    // docker-basics' only edge goes to linux-fundamentals (OS), now hidden.
    expect(ids).not.toContain('docker-basics')
  })

  it('is off by default, so the vault never silently shrinks', () => {
    expect(visibleNodes(miniGraph, base).map((n) => n.id)).toContain('vim-shortcuts')
  })
})
