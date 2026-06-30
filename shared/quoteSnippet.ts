import { prepareMessageContent } from './prepareMessageContent'

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

/** Bare LaTeX (math widget) → display-math snippet for RichText markdown rendering. */
export function prepareQuoteSnippetLatex(latex: string, max = QUOTE_SNIPPET_MAX): string {
  const prepared = prepareMessageContent(latex)
  if (!prepared) {
    return 'Math expression'
  }
  const innerMax = Math.max(max - DISPLAY_MATH_WRAPPER_LEN, 1)
  const inner = truncateQuoteSnippet(prepared, innerMax)
  return `$$${inner}$$`
}
