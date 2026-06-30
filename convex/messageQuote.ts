import { prepareMessageContent } from '../shared/prepareMessageContent'
import {
  prepareQuoteSnippetLatex,
  prepareQuoteSnippetText,
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
    if (type === 'math') {
      const latex =
        (typeof parsed.latex === 'string' ? parsed.latex : '') ||
        (typeof parsed.content === 'string' ? parsed.content : '')
      if (latex.trim()) {
        return prepareMessageContent(latex)
      }
      return 'Math expression'
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
        if (type === 'math') {
          const latex =
            (typeof parsed.latex === 'string' ? parsed.latex : '') ||
            (typeof parsed.content === 'string' ? parsed.content : '')
          if (latex.trim()) {
            return prepareQuoteSnippetLatex(latex)
          }
          return 'Math expression'
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

export type ReplyQuoteContext = {
  role: 'user' | 'assistant'
  text: string
  truncated: boolean
  threadPosition?: number
  threadLength?: number
}

export function formatGroqUserMessageWithReplyContext(
  userText: string,
  quote: ReplyQuoteContext,
): string {
  const roleLabel = quote.role === 'assistant' ? 'assistant' : 'user'
  const positionAttr =
    quote.threadPosition !== undefined && quote.threadLength !== undefined
      ? ` position="${quote.threadPosition} of ${quote.threadLength}"`
      : ''
  const truncatedNote = quote.truncated ? '\n(Quoted text was truncated for length.)' : ''

  return [
    '<reply_context>',
    "The user's NEW message below is a direct reply to the QUOTED message — NOT necessarily the most recent message in the thread.",
    '',
    `<quoted_message role="${roleLabel}"${positionAttr}>`,
    quote.text,
    '</quoted_message>',
    truncatedNote,
    '</reply_context>',
    '',
    '<user_reply>',
    userText,
    '</user_reply>',
  ].join('\n')
}
