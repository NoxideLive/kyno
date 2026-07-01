import { prepareMessageContent } from '../shared/prepareMessageContent'
import { formatGroqReplyContext, type ReplyQuotePromptContext } from '../shared/prompts'
import {
  isNotationWidgetType,
  prepareQuoteSnippetText,
  quoteSnippetForNotationWidget,
  readableTextForNotationWidget,
} from '../shared/quoteSnippet'

export { QUOTE_SNIPPET_MAX, truncateQuoteSnippet } from '../shared/quoteSnippet'

export const QUOTE_FULL_TEXT_MAX = 2000

export function readableTextFromContent(
  content: string,
  role: 'user' | 'assistant',
  contentFormat?: 'widget' | 'text',
): string {
  if (contentFormat !== 'widget') {
    return prepareMessageContent(content)
  }

  const trimmed = content.trim()
  if (!trimmed.startsWith('{')) {
    return prepareMessageContent(content)
  }

  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>
    const type = typeof parsed.type === 'string' ? parsed.type : ''

    if (type === 'response' && typeof parsed.content === 'string') {
      return prepareMessageContent(parsed.content)
    }
    if (type === 'question' && typeof parsed.question === 'string') {
      return prepareMessageContent(parsed.question)
    }
    if (type === 'confirm' && typeof parsed.question === 'string') {
      return prepareMessageContent(parsed.question)
    }
    if (isNotationWidgetType(type)) {
      return readableTextForNotationWidget(parsed)
    }
  } catch {
    // fall through
  }

  return role === 'assistant' ? 'Assistant message' : prepareMessageContent(content)
}

export function quoteSnippetFromContent(
  content: string,
  role: 'user' | 'assistant',
  contentFormat?: 'widget' | 'text',
): string {
  if (contentFormat === 'widget') {
    const trimmed = content.trim()
    if (trimmed.startsWith('{')) {
      try {
        const parsed = JSON.parse(trimmed) as Record<string, unknown>
        const type = typeof parsed.type === 'string' ? parsed.type : ''

        if (type === 'response' && typeof parsed.content === 'string') {
          return prepareQuoteSnippetText(parsed.content)
        }
        if (type === 'question' && typeof parsed.question === 'string') {
          return prepareQuoteSnippetText(parsed.question)
        }
        if (type === 'confirm' && typeof parsed.question === 'string') {
          return prepareQuoteSnippetText(parsed.question)
        }
        if (isNotationWidgetType(type)) {
          return quoteSnippetForNotationWidget(parsed)
        }
      } catch {
        // fall through
      }
    }
  }

  return prepareQuoteSnippetText(readableTextFromContent(content, role, contentFormat))
}

export function quoteTextFromContent(
  content: string,
  role: 'user' | 'assistant',
  contentFormat?: 'widget' | 'text',
  max = QUOTE_FULL_TEXT_MAX,
): { text: string; truncated: boolean } {
  const readable = readableTextFromContent(content, role, contentFormat)
  if (readable.length <= max) {
    return { text: readable, truncated: false }
  }
  return {
    text: `${readable.slice(0, max - 1).trimEnd()}…`,
    truncated: true,
  }
}

export type ReplyQuoteContext = ReplyQuotePromptContext

export function formatGroqUserMessageWithReplyContext(
  userText: string,
  quote: ReplyQuoteContext,
): string {
  return formatGroqReplyContext(userText, quote)
}
