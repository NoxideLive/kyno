import { parseWidgetContent } from '@/lib/widgets'
import type { ChatMessage, ChatRole } from '@/composables/useGroqChat'
import { looksLikeLatex } from '../../shared/looksLikeLatex'
import {
  prepareQuoteNotationLatex,
  prepareQuoteSnippetText,
} from '../../shared/quoteSnippet'

export { QUOTE_SNIPPET_MAX } from '../../shared/quoteSnippet'

export type QuotePreviewKind = 'notation' | 'text'

export type QuotePreview = {
  role: ChatRole
  snippet: string
  kind: QuotePreviewKind
  notationLatex?: string
}

export function quotePreviewFromMessage(
  message: Pick<ChatMessage, 'role' | 'content' | 'contentFormat'>,
): QuotePreview {
  const widget = parseWidgetContent(message.content, message.contentFormat)
  if (widget) {
    switch (widget.type) {
      case 'response':
        return {
          role: message.role,
          kind: 'text',
          snippet: prepareQuoteSnippetText(widget.content),
        }
      case 'question':
        return {
          role: message.role,
          kind: 'text',
          snippet: prepareQuoteSnippetText(widget.question),
        }
      case 'confirm':
        return {
          role: message.role,
          kind: 'text',
          snippet: prepareQuoteSnippetText(widget.question),
        }
      case 'notation': {
        if (widget.title) {
          return {
            role: message.role,
            kind: 'text',
            snippet: prepareQuoteSnippetText(widget.title),
          }
        }
        const content = widget.content.trim()
        if (content && looksLikeLatex(content)) {
          const notationLatex = prepareQuoteNotationLatex(content)
          return {
            role: message.role,
            kind: 'notation',
            notationLatex: notationLatex || undefined,
            snippet: notationLatex || 'Notation',
          }
        }
        return {
          role: message.role,
          kind: 'text',
          snippet: content ? prepareQuoteSnippetText(content) : 'Notation',
        }
      }
      default: {
        const unhandled: never = widget
        return unhandled
      }
    }
  }

  return {
    role: message.role,
    kind: 'text',
    snippet: prepareQuoteSnippetText(message.content),
  }
}

export function quoteSnippetFromMessage(
  message: Pick<ChatMessage, 'role' | 'content' | 'contentFormat'>,
): string {
  return quotePreviewFromMessage(message).snippet
}

export function quoteRoleLabel(role: ChatRole): string {
  return role === 'assistant' ? 'Assistant' : 'You'
}

export function isPersistedMessageId(id: string): boolean {
  return id.length > 0 && !id.includes('-')
}
