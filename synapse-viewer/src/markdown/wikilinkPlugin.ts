import type MarkdownIt from 'markdown-it'
import type { StateInline } from 'markdown-it/index.js'

/**
 * markdown-it inline rule for [[wikilinks]].
 *
 * Supported forms:
 *   [[Target]]             → text="Target"
 *   [[Target|Alias]]       → text="Alias"
 *   [[Target#Heading]]     → text="Target > Heading"
 *   [[Target#Heading|Alias]] → text="Alias"
 *
 * Renders: <a class="wikilink" data-linktext="[[raw]]">display</a>
 * data-linktext holds the full [[...]] string so the viewer can match it to an edge.
 */
export function wikilinkPlugin(md: MarkdownIt): void {
  md.inline.ruler.push('wikilink', (state: StateInline, silent: boolean): boolean => {
    const src = state.src
    const pos = state.pos

    // Must start with [[
    if (src.charCodeAt(pos) !== 0x5b /* [ */ || src.charCodeAt(pos + 1) !== 0x5b /* [ */) {
      return false
    }

    // Find closing ]]
    const start = pos + 2
    const closeIdx = src.indexOf(']]', start)
    if (closeIdx === -1) return false

    const inner = src.slice(start, closeIdx) // e.g. "Target#Heading|Alias"
    if (!inner || inner.includes('[')) return false // nested brackets not allowed

    if (!silent) {
      const raw = `[[${inner}]]`

      // Parse alias: [[Target|Alias]] or [[Target#Heading|Alias]]
      const pipeIdx = inner.indexOf('|')
      let displayText: string

      if (pipeIdx !== -1) {
        // Has explicit alias
        displayText = inner.slice(pipeIdx + 1).trim()
      } else {
        // Check for heading anchor: [[Target#Heading]]
        const hashIdx = inner.indexOf('#')
        if (hashIdx !== -1) {
          const target = inner.slice(0, hashIdx).trim()
          const heading = inner.slice(hashIdx + 1).trim()
          displayText = heading ? `${target} > ${heading}` : target
        } else {
          displayText = inner.trim()
        }
      }

      const token = state.push('wikilink', 'a', 0)
      token.attrSet('class', 'wikilink')
      token.attrSet('data-linktext', raw)
      token.attrSet('href', '#')
      token.content = displayText
    }

    state.pos = closeIdx + 2
    return true
  })

  // Render the wikilink token as <a class="wikilink" data-linktext="[[...]]">text</a>
  md.renderer.rules['wikilink'] = (tokens, idx): string => {
    const token = tokens[idx]
    const linkText = token.attrGet('data-linktext') ?? ''
    const cls = token.attrGet('class') ?? 'wikilink'
    const display = md.utils.escapeHtml(token.content)
    const escapedLinkText = md.utils.escapeHtml(linkText)
    return `<a class="${cls}" data-linktext="${escapedLinkText}" href="#">${display}</a>`
  }
}
