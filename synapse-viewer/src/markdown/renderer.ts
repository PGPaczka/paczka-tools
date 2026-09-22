import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

export function createRenderer(): MarkdownIt {
  return new MarkdownIt({
    html: false,
    linkify: true,
    highlight(str: string, lang: string): string {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return (
            '<pre class="hljs"><code>' +
            hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
            '</code></pre>'
          )
        } catch {
          // fall through to escaped output
        }
      }
      return (
        '<pre class="hljs"><code>' +
        MarkdownIt().utils.escapeHtml(str) +
        '</code></pre>'
      )
    },
  })
}

export function renderMarkdown(source: string, renderer: MarkdownIt): string {
  return renderer.render(source)
}
