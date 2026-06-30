import { prepareMessageContent } from '../../shared/prepareMessageContent'
import { renderLatex, renderMarkdown } from '@/lib/renderMessageContent'

export { prepareMessageContent } from '../../shared/prepareMessageContent'

export type MessageRenderFormat = 'markdown' | 'latex-only'

export type RenderMessageHtmlOptions = {
  displayMode?: boolean
}

export function renderMessageHtml(
  content: string,
  format: MessageRenderFormat,
  options: RenderMessageHtmlOptions = {},
): string {
  const prepared = prepareMessageContent(content)

  switch (format) {
    case 'markdown':
      return renderMarkdown(prepared)
    case 'latex-only':
      return renderLatex(prepared, options.displayMode ?? true)
    default: {
      const unhandled: never = format
      return unhandled
    }
  }
}
