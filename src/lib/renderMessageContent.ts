import katex from 'katex'
import MarkdownIt from 'markdown-it'
import markdownItKatex from 'markdown-it-katex'
import markdownItMultimdTable from 'markdown-it-multimd-table'
import { fromHighlighter } from '@shikijs/markdown-it/core'
import DOMPurify from 'dompurify'
import { createHighlighter } from 'shiki'
import { prepareMessageContent } from '../../shared/prepareMessageContent'

export type MessageContentFormat = 'text' | 'markdown' | 'widget'

const KATEX_SANITIZE_TAGS = [
  'math',
  'semantics',
  'mrow',
  'mi',
  'mn',
  'mo',
  'ms',
  'mtext',
  'mspace',
  'msup',
  'msub',
  'msubsup',
  'mfrac',
  'mroot',
  'msqrt',
  'mtable',
  'mtr',
  'mtd',
  'munder',
  'mover',
  'munderover',
  'mpadded',
  'mphantom',
  'menclose',
  'mstyle',
  'annotation',
] as const

const SHIKI_LANGS = [
  'bash',
  'c',
  'cpp',
  'css',
  'go',
  'html',
  'java',
  'javascript',
  'json',
  'markdown',
  'python',
  'rust',
  'shell',
  'sql',
  'toml',
  'tsx',
  'typescript',
  'vue',
  'yaml',
] as const

const KATEX_SANITIZE_ATTR = [
  'class',
  'style',
  'xmlns',
  'display',
  'encoding',
  'aria-hidden',
  'width',
  'height',
  'colspan',
  'rowspan',
  'mathvariant',
  'displaystyle',
  'scriptlevel',
  'tabindex',
] as const

let markdown: MarkdownIt | null = null
let initPromise: Promise<void> | null = null

function createMarkdownInstance(
  highlighter: Awaited<ReturnType<typeof createHighlighter>>,
): MarkdownIt {
  const instance = new MarkdownIt({
    html: false,
    linkify: true,
    breaks: true,
  })

  instance.use(
    fromHighlighter(highlighter, {
      themes: {
        light: 'github-light',
        dark: 'github-dark',
      },
      defaultLanguage: 'markdown',
      fallbackLanguage: 'markdown',
    }),
  )
  instance.use(markdownItKatex)
  instance.use(markdownItMultimdTable, {
    multiline: true,
    rowspan: true,
    headerless: true,
  })

  const defaultLinkOpen =
    instance.renderer.rules.link_open ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

  instance.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    tokens[idx].attrSet('target', '_blank')
    tokens[idx].attrSet('rel', 'noopener noreferrer')
    return defaultLinkOpen(tokens, idx, options, env, self)
  }

  return instance
}

export function initMessageContentRenderer(): Promise<void> {
  if (!initPromise) {
    initPromise = (async () => {
      const highlighter = await createHighlighter({
        themes: ['github-light', 'github-dark'],
        langs: [...SHIKI_LANGS],
      })
      markdown = createMarkdownInstance(highlighter)
    })()
  }
  return initPromise
}

function getMarkdown(): MarkdownIt {
  if (!markdown) {
    throw new Error('Message content renderer is not initialized')
  }
  return markdown
}

function sanitizeRenderedHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_TAGS: [...KATEX_SANITIZE_TAGS],
    ADD_ATTR: [...KATEX_SANITIZE_ATTR],
  })
}

export function renderMarkdown(content: string): string {
  return sanitizeRenderedHtml(getMarkdown().render(content))
}

/** Render bare LaTeX for math widgets (display mode by default). */
export function renderLatex(latex: string, displayMode = true): string {
  const trimmed = latex.trim()
  if (!trimmed) {
    return ''
  }

  const html = katex.renderToString(trimmed, {
    displayMode,
    throwOnError: false,
  })
  return sanitizeRenderedHtml(html)
}

export function renderMessageContent(
  content: string,
  format: MessageContentFormat,
): string | null {
  const prepared = prepareMessageContent(content)

  switch (format) {
    case 'text':
      return null
    case 'markdown':
      return renderMarkdown(prepared)
    case 'widget':
      return null
    default: {
      const unhandled: never = format
      return unhandled
    }
  }
}
