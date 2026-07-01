import { prepareMessageContent } from './prepareMessageContent'
import { looksLikeLatex } from './looksLikeLatex'

export const QUOTE_SNIPPET_MAX = 120

const DISPLAY_MATH_WRAPPER_LEN = 4 // $$

export function truncateQuoteSnippet(text: string, max = QUOTE_SNIPPET_MAX): string {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (normalized.length <= max) return normalized
  return `${normalized.slice(0, max - 1).trimEnd()}…`
}

/** Normalize math delimiters, then truncate for quote preview / Groq context. */
export function prepareQuoteSnippetText(text: string, max = QUOTE_SNIPPET_MAX): string {
  return truncateQuoteSnippet(prepareMessageContent(text), max)
}

/** Truncate bare LaTeX for quote preview (NotationDisplay) or Groq context. */
export function prepareQuoteNotationLatex(latex: string, max = QUOTE_SNIPPET_MAX): string {
  const prepared = prepareMessageContent(latex)
  if (!prepared) {
    return ''
  }
  return truncateQuoteSnippet(prepared, max)
}

/** @deprecated Use prepareQuoteNotationLatex */
export const prepareQuoteMathLatex = prepareQuoteNotationLatex

/** Bare LaTeX (notation widget) → display-math snippet for RichText markdown rendering. */
export function prepareQuoteSnippetLatex(latex: string, max = QUOTE_SNIPPET_MAX): string {
  const innerMax = Math.max(max - DISPLAY_MATH_WRAPPER_LEN, 1)
  const inner = prepareQuoteNotationLatex(latex, innerMax)
  if (!inner) {
    return 'Notation'
  }
  return `$$${inner}$$`
}

export function notationContentFromWidgetFields(parsed: Record<string, unknown>): string {
  const content = typeof parsed.content === 'string' ? parsed.content.trim() : ''
  const latex = typeof parsed.latex === 'string' ? parsed.latex.trim() : ''
  return content || latex
}

export function isNotationWidgetType(type: string): boolean {
  return type === 'notation' || type === 'math'
}

export function quoteSnippetForNotationWidget(parsed: Record<string, unknown>): string {
  const title = typeof parsed.title === 'string' ? parsed.title.trim() : ''
  const content = notationContentFromWidgetFields(parsed)

  if (title) {
    return prepareQuoteSnippetText(title)
  }

  if (content) {
    if (looksLikeLatex(content)) {
      return prepareQuoteSnippetLatex(content)
    }
    return prepareQuoteSnippetText(content)
  }

  return 'Notation'
}

export function readableTextForNotationWidget(parsed: Record<string, unknown>): string {
  const title = typeof parsed.title === 'string' ? parsed.title.trim() : ''
  const content = notationContentFromWidgetFields(parsed)

  if (title) {
    return prepareMessageContent(title)
  }

  if (content) {
    return prepareMessageContent(content)
  }

  return 'Notation'
}
