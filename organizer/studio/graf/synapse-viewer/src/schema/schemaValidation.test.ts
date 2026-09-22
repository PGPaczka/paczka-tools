import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'

const schemaPath = resolve(__dirname, '../../../schema/graph.schema.v2.json')
const graphPath = resolve(__dirname, '../../public/graph.json')

const rawSchema = JSON.parse(readFileSync(schemaPath, 'utf-8'))
const rawGraph = JSON.parse(readFileSync(graphPath, 'utf-8'))

const ajv = new Ajv({ strict: true, allErrors: true })
addFormats(ajv)
const validate = ajv.compile(rawSchema)

describe('graph.json schema validation', () => {
  it('public/graph.json is valid against graph.schema.v2.json', () => {
    const valid = validate(rawGraph)
    if (!valid) {
      console.error('Validation errors:', JSON.stringify(validate.errors, null, 2))
    }
    expect(valid).toBe(true)
  })

  it('schema has schemaVersion 2 const', () => {
    expect(rawSchema.properties.schemaVersion.const).toBe(2)
  })

  it('graph has correct structure', () => {
    expect(rawGraph.schemaVersion).toBe(2)
    expect(rawGraph.nodes).toBeInstanceOf(Array)
    expect(rawGraph.edges).toBeInstanceOf(Array)
    expect(rawGraph.warnings).toBeInstanceOf(Array)
    expect(rawGraph.vault).toBeDefined()
  })

  it('ghost nodes have required fields', () => {
    const ghosts = rawGraph.nodes.filter((n: { kind: string }) => n.kind === 'ghost')
    for (const ghost of ghosts) {
      expect(ghost).toHaveProperty('id')
      expect(ghost).toHaveProperty('title')
      expect(ghost).toHaveProperty('referencedBy')
      expect(ghost).toHaveProperty('referenceCount')
      expect(ghost.referenceCount).toBeGreaterThanOrEqual(1)
    }
  })

  it('real nodes have required fields', () => {
    const real = rawGraph.nodes.filter((n: { kind: string }) => n.kind === 'real')
    for (const node of real) {
      expect(node).toHaveProperty('id')
      expect(node).toHaveProperty('title')
      expect(node).toHaveProperty('path')
      expect(node).toHaveProperty('category')
      expect(node).toHaveProperty('tags')
      expect(node).toHaveProperty('aliases')
      expect(node).toHaveProperty('excerpt')
      expect(node).toHaveProperty('wordCount')
    }
  })

  it('edges reference valid node ids', () => {
    const ids = new Set(rawGraph.nodes.map((n: { id: string }) => n.id))
    for (const edge of rawGraph.edges) {
      expect(ids.has(edge.source), `source "${edge.source}" not in nodes`).toBe(true)
      expect(ids.has(edge.target), `target "${edge.target}" not in nodes`).toBe(true)
    }
  })

  it('generatedAt is a valid ISO date-time string', () => {
    const d = new Date(rawGraph.generatedAt)
    expect(Number.isNaN(d.getTime())).toBe(false)
  })

  it('rejects invalid schema version', () => {
    const bad = { ...rawGraph, schemaVersion: 1 }
    expect(validate(bad)).toBe(false)
  })
})
