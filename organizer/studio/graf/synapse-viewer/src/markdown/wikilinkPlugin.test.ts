import { describe, it, expect, beforeEach } from 'vitest'
import MarkdownIt from 'markdown-it'
import { wikilinkPlugin } from './wikilinkPlugin'

let md: MarkdownIt

beforeEach(() => {
  md = new MarkdownIt({ html: false })
  md.use(wikilinkPlugin)
})

describe('wikilinkPlugin', () => {
  it('renders [[Target]] with correct class, data-linktext and text', () => {
    const html = md.render('[[Target]]')
    expect(html).toContain('class="wikilink"')
    expect(html).toContain('data-linktext="[[Target]]"')
    expect(html).toContain('>Target<')
  })

  it('renders [[Target|Alias]] using Alias as display text', () => {
    const html = md.render('[[Target|Alias]]')
    expect(html).toContain('data-linktext="[[Target|Alias]]"')
    expect(html).toContain('>Alias<')
    expect(html).not.toContain('>Target<')
  })

  it('renders [[Target#Heading]] with "Target > Heading" as display text', () => {
    const html = md.render('[[Target#Heading]]')
    expect(html).toContain('data-linktext="[[Target#Heading]]"')
    expect(html).toContain('Target &gt; Heading')
  })

  it('renders [[Target#Heading|Alias]] using Alias as display text', () => {
    const html = md.render('[[Target#Heading|Alias]]')
    expect(html).toContain('data-linktext="[[Target#Heading|Alias]]"')
    expect(html).toContain('>Alias<')
  })

  it('does not affect regular markdown links', () => {
    const html = md.render('[regular link](https://example.com)')
    expect(html).not.toContain('wikilink')
    expect(html).toContain('href="https://example.com"')
  })

  it('does not affect regular markdown text', () => {
    const html = md.render('Just some plain text.')
    expect(html).not.toContain('class="wikilink"')
    expect(html).toContain('Just some plain text')
  })

  it('handles wikilinks inline with surrounding text', () => {
    const html = md.render('See [[Target]] for details.')
    expect(html).toContain('wikilink')
    expect(html).toContain('See')
    expect(html).toContain('for details')
  })

  it('preserves other markdown (bold, italic)', () => {
    const html = md.render('**bold** and [[Note]]')
    expect(html).toContain('<strong>bold</strong>')
    expect(html).toContain('class="wikilink"')
  })
})
