import assert from 'node:assert/strict'
import MarkdownIt from 'markdown-it'
import markdownItKatex from 'markdown-it-katex'
import { prepareMessageContent } from './prepareMessageContent'
import { wrapBareLatexInMarkdown } from './wrapBareLatexInMarkdown'

const md = new MarkdownIt({ html: false, breaks: true }).use(markdownItKatex)

const USER_EXAMPLE = `The derivative of f(x)=x^n is given by the power rule:

$$f'(x)=\\frac{d}{dx}\\,x^n=n\\,x^{n-1}
This formula holds for any real exponent n.`

function renderPipeline(raw: string): string {
  const prepared = prepareMessageContent(raw)
  const wrapped = wrapBareLatexInMarkdown(prepared)
  return md.render(wrapped)
}

const html = renderPipeline(USER_EXAMPLE)

assert.match(html, /katex-display/, 'display math should render')
assert.match(html, /<p>This formula holds for any real exponent n\.<\/p>/, 'prose after equation must be its own paragraph')
assert.doesNotMatch(
  html.match(/<annotation encoding="application\/x-tex">[\s\S]*?<\/annotation>/)?.[0] ?? '',
  /This formula holds/,
  'prose must not appear inside math annotation',
)

const wrapped = wrapBareLatexInMarkdown(prepareMessageContent(USER_EXAMPLE))
assert.match(wrapped, /\$\$f'\(x\)=\\frac\{d\}\{dx\}[\s\S]*\$\$/, 'display math must be closed')
assert.doesNotMatch(wrapped, /\$\$\$\$/, 'must not double-wrap display delimiters')

const parenHtml = renderPipeline('The derivative of (f(x)=x^n) is given by the power rule:')
assert.match(parenHtml, /katex/, 'parenthetical inline math should render')
assert.match(parenHtml, /given by the power rule/, 'surrounding prose should remain')

console.log('wrapBareLatexInMarkdown manual tests passed')
