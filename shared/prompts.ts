/** Shared LLM prompt fragments for Kyno (Groq). Single source of truth for widget rules. */

export const WIDGET_BATCH_FORMAT = '{"widgets":[...]}'

export const NOTATION_EMBEDDED_HINT =
  'Notation (equations, formulas, chemical symbols) must not appear in "question" or "confirm" text. Split into a preceding "notation" widget (title + content) and a separate "question" or "confirm" widget with a short prompt only.'

const WIDGET_FLAT_SHAPE = `{
  "widgets": [{
    "type": "response" | "question" | "confirm" | "notation",
    "title": "<label or empty>",
    "content": "<markdown, LaTeX, or empty>",
    "question": "<prompt or empty>",
    "suggestedAnswers": ["..."] or []
  }]
}`

const NOTATION_RULE = `Notation (mandatory): Any equation, formula, or chemical symbol → separate "notation" widget (non-empty title + content). Never embed display notation only in question/confirm/response.
MCQ or confirm with notation → return widgets in order: [notation, question|confirm]; keep the prompt short in the second widget.
Confirm (yes/no) about an equation → ALWAYS two widgets [notation, confirm]; put the equation ONLY in notation.content, never in confirm.question or confirm.content. Never return confirm alone when an equation is involved.
Inline math inside response prose: wrap with $...$ or $$...$$; prefer a notation widget for display equations.`

const WIDGET_DECISION = `Pick one type per widget (check in order):
1. Display-only notation (equations, formulas, chemical symbols) → notation
   - User asks to show, display, or state a formula/equation/chemical symbol → notation (optional brief response before notation)
2. User must confirm, proceed, or signal understanding → confirm
   - suggestedAnswers are ONLY ["Yes","No"] or ["Yes","No","Not sure"] — never topic names or factual choices
   - Use when the user asks: "Ready to continue?", "Are you ready?", "Does that make sense?", "Do you understand?"
   - Use when the user requests yes/no/not-sure answers about understanding or readiness
   - If the message contains an equation/formula AND needs yes/no → [notation, confirm] (never confirm alone)
   - NOT for picking topics, preferences, or factual answers — those are question
3. User must pick one of 2–4 substantive options → question
   - Options are topics, values, or preferences — NOT Yes/No/Not sure
   - "A or B?", "which topic", "pick a color", "prefer X or Y" → question with those options
   - Rhetorical questions you answer in prose → response, not question
4. Otherwise → response (explanations, greetings, prose answers)`

const WIDGET_TYPE_RULES = `Per-type (invalid output is rejected):
- response: non-empty content; title "", question "", suggestedAnswers []
- notation: non-empty title + content (LaTeX without $ delimiters, or text like H₂O); question "", suggestedAnswers []
- confirm: non-empty question (short, no notation); suggestedAnswers 2–3 (Yes/No or Yes/No/Not sure only); content optional; title ""
- question: non-empty question (short, no notation); suggestedAnswers 2–4 (substantive options, never Yes/No/Not sure); content "", title ""`

const WIDGET_EXAMPLES = `Examples:
{"widgets":[{"type":"response","title":"","content":"The power rule differentiates x^n.","question":"","suggestedAnswers":[]},{"type":"notation","title":"Power rule","content":"\\\\frac{d}{dx}x^n = nx^{n-1}","question":"","suggestedAnswers":[]}]}
{"widgets":[{"type":"notation","title":"Equation","content":"2x + 5 = 17","question":"","suggestedAnswers":[]},{"type":"question","title":"","content":"","question":"What is x?","suggestedAnswers":["6","7","8","9"]}]}
{"widgets":[{"type":"question","title":"","content":"","question":"What is the capital of France?","suggestedAnswers":["Paris","London","Berlin","Madrid"]}]}
{"widgets":[{"type":"question","title":"","content":"","question":"Do you prefer studying in the morning or at night?","suggestedAnswers":["Morning","Night"]}]}
{"widgets":[{"type":"confirm","title":"","content":"","question":"Ready to continue?","suggestedAnswers":["Yes","No"]}]}
{"widgets":[{"type":"confirm","title":"","content":"","question":"Does that make sense?","suggestedAnswers":["Yes","No"]}]}
{"widgets":[{"type":"confirm","title":"","content":"","question":"Do you understand the concept?","suggestedAnswers":["Yes","No","Not sure"]}]}
{"widgets":[{"type":"notation","title":"Water","content":"H_2O","question":"","suggestedAnswers":[]}]}
{"widgets":[{"type":"notation","title":"Equation","content":"2x + 5 = 17","question":"","suggestedAnswers":[]},{"type":"confirm","title":"","content":"","question":"Does this mean x is 6?","suggestedAnswers":["Yes","No"]}]}`

export const WIDGET_SYSTEM_PROMPT = `You are a helpful assistant in Kyno chat.

Every reply MUST be ${WIDGET_BATCH_FORMAT}. Prior assistant turns may show one widget each; always use the batch format now.

${WIDGET_FLAT_SHAPE}

Use multiple widgets in order when needed (e.g. response then notation). Do not mix prose and display notation in one widget.

${NOTATION_RULE}

${WIDGET_DECISION}

${WIDGET_TYPE_RULES}

${WIDGET_EXAMPLES}`

export const WIDGET_CORRECTION_PREFIX = `[Kyno validation — not shown to the user] Your previous widget JSON was invalid. Reply with exactly one corrected ${WIDGET_BATCH_FORMAT} object.`

export function jsonInvalidRetryHint(): string {
  return `Your reply was not valid JSON. Respond with ${WIDGET_BATCH_FORMAT} only.`
}

export function batchInvalidRetryHint(detail?: string): string {
  const trimmed = detail?.trim() ?? ''
  if (trimmed && !trimmed.startsWith('Assistant reply')) {
    return `Groq rejected the output: ${trimmed}. Reply with ${WIDGET_BATCH_FORMAT} where every item follows the widget rules.`
  }
  return `Your JSON must be ${WIDGET_BATCH_FORMAT} with at least one widget.`
}

export function flatShapeRetryHint(prefix: string, zodDetail: string | null): string {
  const base = `${prefix}Did not match the required widget shape (type, title, content, question, suggestedAnswers).`
  return zodDetail ? `${base} ${zodDetail}` : base
}

export function titleGenerationPrompt(userMessage: string): string {
  return `Title this chat in 3–6 words. Reply with only the title — no quotes, no trailing punctuation.\n\n${userMessage}`
}

export type ReplyQuotePromptContext = {
  role: 'user' | 'assistant'
  text: string
  truncated: boolean
  threadPosition?: number
  threadLength?: number
}

export function formatGroqReplyContext(userText: string, quote: ReplyQuotePromptContext): string {
  const roleLabel = quote.role === 'assistant' ? 'assistant' : 'user'
  const positionAttr =
    quote.threadPosition !== undefined && quote.threadLength !== undefined
      ? ` position="${quote.threadPosition} of ${quote.threadLength}"`
      : ''
  const truncatedNote = quote.truncated ? '\n(Quoted text truncated.)' : ''

  return [
    '<reply_context>',
    'User reply targets the quoted message (not necessarily the latest in thread).',
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
