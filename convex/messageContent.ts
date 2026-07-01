import { prepareMessageContent } from '../shared/prepareMessageContent'

export { prepareMessageContent }

/** Normalize stored message bodies — text or widget JSON string fields. */
export function prepareStoredMessageContent(
  content: string,
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
      parsed.content = prepareMessageContent(parsed.content)
    } else if (type === 'question' && typeof parsed.question === 'string') {
      parsed.question = prepareMessageContent(parsed.question)
    } else if (type === 'confirm') {
      if (typeof parsed.content === 'string') {
        parsed.content = prepareMessageContent(parsed.content)
      }
      if (typeof parsed.question === 'string') {
        parsed.question = prepareMessageContent(parsed.question)
      }
    } else if (type === 'notation' || type === 'math') {
      const notationContent =
        (typeof parsed.content === 'string' ? parsed.content : '') ||
        (typeof parsed.latex === 'string' ? parsed.latex : '')
      const prepared = prepareMessageContent(notationContent)
      parsed.content = prepared
      if (typeof parsed.latex === 'string') {
        parsed.latex = prepared
      }
      if (typeof parsed.title === 'string') {
        parsed.title = prepareMessageContent(parsed.title)
      }
    }

    return JSON.stringify(parsed)
  } catch {
    return content
  }
}
