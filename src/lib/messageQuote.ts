import { parseWidgetContent } from '@/lib/widgets'
import type { ChatMessage, ChatRole } from '@/composables/useGroqChat'
import {
  prepareQuoteSnippetLatex,
  prepareQuoteSnippetText,
} from '../../shared/quoteSnippet'

export { QUOTE_SNIPPET_MAX } from '../../shared/quoteSnippet'

export function quoteSnippetFromMessage(message: Pick<ChatMessage, 'role' | 'content' | 'contentFormat'>): string {
  const widget = parseWidgetContent(message.content, message.contentFormat)
  if (widget) {
    switch (widget.type) {
      case 'response':
        return prepareQuoteSnippetText(widget.content)
      case 'question':
        return prepareQuoteSnippetText(widget.question)
      case 'confirm':
        return prepareQuoteSnippetText(widget.question)
      case 'math':
        return widget.latex.trim()
          ? prepareQuoteSnippetLatex(widget.latex)
          : 'Math expression'
      default: {
        const unhandled: never = widget
        return unhandled
      }
    }
  }

  return prepareQuoteSnippetText(message.content)
}

export function quoteRoleLabel(role: ChatRole): string {
  return role === 'assistant' ? 'Assistant' : 'You'
}

export function isPersistedMessageId(id: string): boolean {
  return id.length > 0 && !id.includes('-')
}
