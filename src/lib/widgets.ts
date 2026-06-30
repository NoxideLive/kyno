export type KynoWidgetResponse = {
  type: 'response'
  content: string
}

export type KynoWidgetQuestion = {
  type: 'question'
  question: string
  suggestedAnswers: string[]
}

export type KynoWidgetConfirm = {
  type: 'confirm'
  question: string
  suggestedAnswers: string[]
  content: string
}

export type KynoWidgetMath = {
  type: 'math'
  latex: string
}

export type KynoWidget =
  | KynoWidgetResponse
  | KynoWidgetQuestion
  | KynoWidgetConfirm
  | KynoWidgetMath

const MIN_QUESTION_SUGGESTIONS = 2
const MAX_QUESTION_SUGGESTIONS = 4
const MIN_CONFIRM_OPTIONS = 2
const MAX_CONFIRM_OPTIONS = 3

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function cleanSuggestedAnswers(answers: string[], max: number): string[] {
  return answers
    .map((answer) => answer.trim())
    .filter((answer) => answer.length > 0)
    .slice(0, max)
}

function stripLatexDelimiters(raw: string): string {
  let latex = raw.trim()
  if (latex.startsWith('$$') && latex.endsWith('$$')) {
    latex = latex.slice(2, -2).trim()
  } else if (latex.startsWith('$') && latex.endsWith('$') && !latex.startsWith('$$')) {
    latex = latex.slice(1, -1).trim()
  }
  return latex
}

function mathLatexFromWidgetFields(value: Record<string, unknown>): string {
  const content = typeof value.content === 'string' ? value.content.trim() : ''
  const latexField = typeof value.latex === 'string' ? value.latex.trim() : ''
  return stripLatexDelimiters(content || latexField)
}

function normalizeFlatWidget(value: Record<string, unknown>): KynoWidget | null {
  if (value.type === 'math') {
    const latex = mathLatexFromWidgetFields(value)
    const question = typeof value.question === 'string' ? value.question.trim() : ''
    const suggestedAnswers = isStringArray(value.suggestedAnswers)
      ? cleanSuggestedAnswers(value.suggestedAnswers, MAX_QUESTION_SUGGESTIONS)
      : []

    if (!latex || question || suggestedAnswers.length > 0) {
      return null
    }

    return { type: 'math', latex }
  }

  if (value.type === 'response' && typeof value.content === 'string') {
    const content = value.content.trim()
    const question = typeof value.question === 'string' ? value.question.trim() : ''
    const suggestedAnswers = isStringArray(value.suggestedAnswers)
      ? cleanSuggestedAnswers(value.suggestedAnswers, MAX_QUESTION_SUGGESTIONS)
      : []

    if (!content || question || suggestedAnswers.length > 0) {
      return null
    }

    return { type: 'response', content }
  }

  if (
    value.type === 'confirm' &&
    typeof value.question === 'string' &&
    isStringArray(value.suggestedAnswers)
  ) {
    const question = value.question.trim()
    const content = typeof value.content === 'string' ? value.content.trim() : ''
    const suggestedAnswers = cleanSuggestedAnswers(value.suggestedAnswers, MAX_CONFIRM_OPTIONS)

    if (
      !question ||
      suggestedAnswers.length < MIN_CONFIRM_OPTIONS ||
      suggestedAnswers.length > MAX_CONFIRM_OPTIONS
    ) {
      return null
    }

    return { type: 'confirm', question, suggestedAnswers, content }
  }

  if (
    value.type === 'question' &&
    typeof value.question === 'string' &&
    isStringArray(value.suggestedAnswers)
  ) {
    const suggestedAnswers = cleanSuggestedAnswers(value.suggestedAnswers, MAX_QUESTION_SUGGESTIONS)
    const question = value.question.trim()
    const content = typeof value.content === 'string' ? value.content.trim() : ''

    if (
      !question ||
      content ||
      suggestedAnswers.length < MIN_QUESTION_SUGGESTIONS ||
      suggestedAnswers.length > MAX_QUESTION_SUGGESTIONS
    ) {
      return null
    }

    return { type: 'question', question, suggestedAnswers }
  }

  return null
}

function parseWidgetObject(value: unknown): KynoWidget | null {
  if (!isRecord(value) || typeof value.type !== 'string') {
    return null
  }

  return normalizeFlatWidget(value)
}

/** Parse assistant content as a widget; returns null for plain text or invalid JSON. */
export function parseWidgetContent(
  content: string,
  contentFormat?: 'widget' | 'text',
): KynoWidget | null {
  if (contentFormat === 'text') {
    return null
  }

  const trimmed = content.trim()
  if (!trimmed.startsWith('{')) {
    return null
  }

  try {
    return parseWidgetObject(JSON.parse(trimmed))
  } catch {
    return null
  }
}

export function isInteractiveWidget(
  widget: KynoWidget,
): widget is KynoWidgetQuestion | KynoWidgetConfirm {
  return widget.type === 'question' || widget.type === 'confirm'
}
