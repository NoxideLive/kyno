import { z } from 'zod'

/**
 * Flat widget schema for Groq strict JSON mode.
 * Groq does not allow anyOf/oneOf at the top level of a strict schema.
 * All fields are required; unused fields are empty string / empty array.
 */
export const kynoWidgetFlatSchema = z
  .object({
    type: z.enum(['response', 'question', 'confirm', 'math']),
    content: z.string(),
    question: z.string(),
    suggestedAnswers: z.array(z.string()),
  })
  .strict()

export type KynoWidgetFlat = z.infer<typeof kynoWidgetFlatSchema>

export const kynoWidgetBatchSchema = z
  .object({
    widgets: z.array(kynoWidgetFlatSchema).min(1),
  })
  .strict()

export type KynoWidgetBatch = z.infer<typeof kynoWidgetBatchSchema>

/** Discriminated union for runtime use after normalization. */
export const kynoWidgetResponseSchema = z
  .object({
    type: z.literal('response'),
    content: z.string(),
  })
  .strict()

export const kynoWidgetQuestionSchema = z
  .object({
    type: z.literal('question'),
    question: z.string(),
    suggestedAnswers: z.array(z.string()),
  })
  .strict()

export const kynoWidgetConfirmSchema = z
  .object({
    type: z.literal('confirm'),
    question: z.string(),
    suggestedAnswers: z.array(z.string()),
    content: z.string(),
  })
  .strict()

export const kynoWidgetMathSchema = z
  .object({
    type: z.literal('math'),
    latex: z.string(),
  })
  .strict()

export const kynoWidgetSchema = z.discriminatedUnion('type', [
  kynoWidgetResponseSchema,
  kynoWidgetQuestionSchema,
  kynoWidgetConfirmSchema,
  kynoWidgetMathSchema,
])

export type KynoWidget = z.infer<typeof kynoWidgetSchema>

const flatWidgetItemSchema = {
  type: 'object',
  properties: {
    type: { type: 'string', enum: ['response', 'question', 'confirm', 'math'] },
    content: { type: 'string' },
    question: { type: 'string' },
    suggestedAnswers: {
      type: 'array',
      items: { type: 'string' },
    },
  },
  required: ['type', 'content', 'question', 'suggestedAnswers'],
  additionalProperties: false,
} as const

/** JSON Schema for Groq structured outputs — batch of flat widgets. */
export const KYNO_WIDGET_JSON_SCHEMA = {
  type: 'object',
  properties: {
    widgets: {
      type: 'array',
      items: flatWidgetItemSchema,
      minItems: 1,
    },
  },
  required: ['widgets'],
  additionalProperties: false,
} as const

export const MIN_QUESTION_SUGGESTIONS = 2
export const MAX_QUESTION_SUGGESTIONS = 4
export const MIN_CONFIRM_OPTIONS = 2
export const MAX_CONFIRM_OPTIONS = 3

export const WIDGET_SYSTEM_PROMPT = `You are a helpful assistant in Kyno chat.

Every reply MUST be a JSON object with a "widgets" array (one or more widgets).
Always reply with {"widgets":[...]} even though prior assistant turns may show one widget per message.

{
  "widgets": [
    {
      "type": "response" | "question" | "confirm" | "math",
      "content": "<markdown, LaTeX, or empty>",
      "question": "<question text or empty>",
      "suggestedAnswers": ["option1", ...] or []
    }
  ]
}

Use multiple widgets in order when needed — e.g. a "response" for explanation, then a separate "math" widget for an equation. Do not put prose and display math in the same widget.

## Decision order (pick one widget type per array item)
1. Display-only math (equation, expression, step)? → "math" (LaTeX only in "content", no surrounding text)
2. Yes/No (or Yes/No/Not sure)? → "confirm"
3. Pick one of 2–4 distinct options? → "question"
4. Otherwise → "response"

## Per-type requirements (strict — invalid output is rejected)
- "response": non-empty markdown "content"; "question" ""; "suggestedAnswers" []
- "math": non-empty LaTeX in "content" (no $ delimiters, no prose); "question" ""; "suggestedAnswers" []
- "confirm": non-empty "question"; "suggestedAnswers" 2–3 labels; "content" optional context or ""
- "question": non-empty "question"; "suggestedAnswers" 2–4 labels; "content" ""

## Examples
Explanation then formula:
{"widgets":[
  {"type":"response","content":"The quadratic formula solves ax²+bx+c=0.","question":"","suggestedAnswers":[]},
  {"type":"math","content":"x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}","question":"","suggestedAnswers":[]}
]}

Confirm only:
{"widgets":[{"type":"confirm","content":"","question":"Ready for practice?","suggestedAnswers":["Yes","No"]}]}`

export type WidgetParseFailure = {
  stage: 'json' | 'batch' | 'flat' | 'normalize'
  message: string
  zodIssues?: unknown
  raw: string
  widgetIndex?: number
}

export type WidgetParseResult =
  | { ok: true; widgets: KynoWidget[] }
  | { ok: false; failure: WidgetParseFailure }

/** Fill missing flat-schema fields Groq sometimes omits on structurally valid objects. */
export function fillFlatWidgetDefaults(parsed: unknown): unknown {
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return parsed
  }

  const obj = parsed as Record<string, unknown>
  return {
    type: obj.type,
    content: typeof obj.content === 'string' ? obj.content : '',
    question: typeof obj.question === 'string' ? obj.question : '',
    suggestedAnswers: Array.isArray(obj.suggestedAnswers)
      ? obj.suggestedAnswers.filter((item): item is string => typeof item === 'string')
      : [],
  }
}

export function cleanSuggestedAnswers(
  answers: string[],
  max = MAX_QUESTION_SUGGESTIONS,
): string[] {
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

function normalizeFlatToWidget(flat: KynoWidgetFlat): { widget: KynoWidget } | { reason: string } {
  if (flat.type === 'math') {
    const latex = stripLatexDelimiters(flat.content)
    const question = flat.question.trim()
    const suggestedAnswers = cleanSuggestedAnswers(flat.suggestedAnswers)

    if (!latex) {
      return {
        reason:
          'type "math" requires non-empty LaTeX in "content". Put explanation in a separate "response" widget.',
      }
    }

    if (question || suggestedAnswers.length > 0) {
      return {
        reason: 'type "math" requires "question" to be "" and "suggestedAnswers" to be [].',
      }
    }

    const normalized = kynoWidgetMathSchema.safeParse({ type: 'math', latex })
    return normalized.success ? { widget: normalized.data } : { reason: 'Invalid math widget.' }
  }

  if (flat.type === 'response') {
    const content = flat.content.trim()
    const question = flat.question.trim()
    const suggestedAnswers = cleanSuggestedAnswers(flat.suggestedAnswers)

    if (!content) {
      if (question || suggestedAnswers.length > 0) {
        return {
          reason:
            'type "response" requires non-empty "content". Put your message in "content", set "question" to "", and "suggestedAnswers" to []. If the user should choose options, use type "question" or "confirm" instead.',
        }
      }
      return { reason: 'type "response" requires non-empty "content".' }
    }

    if (question || suggestedAnswers.length > 0) {
      return {
        reason:
          'type "response" requires "question" to be "" and "suggestedAnswers" to be []. Put your full message in "content" only.',
      }
    }

    const normalized = kynoWidgetResponseSchema.safeParse({ type: 'response', content })
    return normalized.success ? { widget: normalized.data } : { reason: 'Invalid response widget.' }
  }

  if (flat.type === 'confirm') {
    const question = flat.question.trim()
    const content = flat.content.trim()
    const suggestedAnswers = cleanSuggestedAnswers(flat.suggestedAnswers, MAX_CONFIRM_OPTIONS)

    if (!question) {
      return {
        reason:
          'type "confirm" requires non-empty "question". Use type "response" if you are not asking for yes/no.',
      }
    }

    if (suggestedAnswers.length < MIN_CONFIRM_OPTIONS) {
      return {
        reason: `type "confirm" requires 2–3 non-empty "suggestedAnswers" (got ${suggestedAnswers.length}). Prefer ["Yes","No"] or ["Yes","No","Not sure"].`,
      }
    }

    if (suggestedAnswers.length > MAX_CONFIRM_OPTIONS) {
      return {
        reason: `type "confirm" allows at most ${MAX_CONFIRM_OPTIONS} "suggestedAnswers".`,
      }
    }

    const normalized = kynoWidgetConfirmSchema.safeParse({
      type: 'confirm',
      question,
      suggestedAnswers,
      content,
    })
    return normalized.success ? { widget: normalized.data } : { reason: 'Invalid confirm widget.' }
  }

  const question = flat.question.trim()
  const suggestedAnswers = cleanSuggestedAnswers(flat.suggestedAnswers)
  const content = flat.content.trim()

  if (!question) {
    return {
      reason:
        'type "question" requires non-empty "question". Use type "response" for statements without tap-able choices.',
    }
  }

  if (content) {
    return {
      reason: 'type "question" requires "content" to be "". Put the prompt in "question" only.',
    }
  }

  if (suggestedAnswers.length < MIN_QUESTION_SUGGESTIONS) {
    return {
      reason: `type "question" requires 2–4 non-empty "suggestedAnswers" (got ${suggestedAnswers.length}). Add distinct options or use type "response" / "confirm" instead.`,
    }
  }

  if (suggestedAnswers.length > MAX_QUESTION_SUGGESTIONS) {
    return {
      reason: `type "question" allows at most ${MAX_QUESTION_SUGGESTIONS} "suggestedAnswers".`,
    }
  }

  const normalized = kynoWidgetQuestionSchema.safeParse({
    type: 'question',
    question,
    suggestedAnswers,
  })
  return normalized.success ? { widget: normalized.data } : { reason: 'Invalid question widget.' }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function flatItemsFromParsed(parsed: unknown, applyDefaults: boolean): KynoWidgetFlat[] | null {
  if (isRecord(parsed) && Array.isArray(parsed.widgets)) {
    const batch = kynoWidgetBatchSchema.safeParse({
      widgets: parsed.widgets.map((item) =>
        applyDefaults ? fillFlatWidgetDefaults(item) : item,
      ),
    })
    return batch.success ? batch.data.widgets : null
  }

  if (isRecord(parsed) && typeof parsed.type === 'string') {
    const candidate = applyDefaults ? fillFlatWidgetDefaults(parsed) : parsed
    const flat = kynoWidgetFlatSchema.safeParse(candidate)
    return flat.success ? [flat.data] : null
  }

  return null
}

export function widgetRetryHint(failure: WidgetParseFailure): string {
  const prefix =
    failure.widgetIndex !== undefined ? `Widget ${failure.widgetIndex + 1}: ` : ''

  if (failure.stage === 'json') {
    return 'Your reply was not valid JSON. Respond with {"widgets":[...]} only.'
  }

  if (failure.stage === 'batch') {
    const detail = failure.message?.trim() ?? ''
    if (detail && !detail.startsWith('Assistant reply')) {
      return `Groq rejected the output: ${detail}. Reply with {"widgets":[...]} where every item follows the widget rules.`
    }
    return 'Your JSON must be {"widgets":[...]} with at least one widget.'
  }

  if (failure.stage === 'flat') {
    const zodDetail = formatZodIssues(failure.zodIssues)
    const base = `${prefix}Did not match the required widget shape (type, content, question, suggestedAnswers).`
    return zodDetail ? `${base} ${zodDetail}` : base
  }

  return `${prefix}${failure.message?.trim() || 'Widget validation failed.'}`
}

function formatZodIssues(zodIssues: unknown): string | null {
  if (!Array.isArray(zodIssues) || zodIssues.length === 0) {
    return null
  }

  const parts = zodIssues
    .slice(0, 4)
    .map((issue) => {
      if (typeof issue !== 'object' || issue === null) return null
      const path = 'path' in issue && Array.isArray(issue.path) ? issue.path.join('.') : ''
      const message = 'message' in issue && typeof issue.message === 'string' ? issue.message : ''
      if (!message) return null
      return path ? `${path}: ${message}` : message
    })
    .filter((part): part is string => part !== null)

  if (parts.length === 0) {
    return null
  }

  return `Issues: ${parts.join('; ')}.`
}

export function parseKynoWidgetBatchDetailed(
  raw: string,
  options?: { applyDefaults?: boolean },
): WidgetParseResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return {
      ok: false,
      failure: {
        stage: 'json',
        message: 'Assistant reply was not valid JSON.',
        raw,
      },
    }
  }

  const applyDefaults = options?.applyDefaults ?? false
  const items = flatItemsFromParsed(parsed, applyDefaults)
  if (!items) {
    const zodIssues =
      isRecord(parsed) && Array.isArray(parsed.widgets)
        ? kynoWidgetBatchSchema.safeParse({
            widgets: parsed.widgets.map((item) =>
              applyDefaults ? fillFlatWidgetDefaults(item) : item,
            ),
          }).error?.issues
        : isRecord(parsed) && typeof parsed.type === 'string'
          ? kynoWidgetFlatSchema.safeParse(
              applyDefaults ? fillFlatWidgetDefaults(parsed) : parsed,
            ).error?.issues
          : kynoWidgetBatchSchema.safeParse(parsed).error?.issues

    return {
      ok: false,
      failure: {
        stage: isRecord(parsed) && !Array.isArray(parsed.widgets) && !parsed.type ? 'batch' : 'flat',
        message: 'Assistant reply must be {"widgets":[...]} or a legacy single widget object.',
        zodIssues,
        raw,
      },
    }
  }

  const widgets: KynoWidget[] = []
  for (let index = 0; index < items.length; index++) {
    const normalized = normalizeFlatToWidget(items[index])
    if ('reason' in normalized) {
      return {
        ok: false,
        failure: {
          stage: 'normalize',
          message: normalized.reason,
          raw,
          widgetIndex: index,
        },
      }
    }
    widgets.push(normalized.widget)
  }

  return { ok: true, widgets }
}

/** @deprecated Use parseKynoWidgetBatchDetailed — parses first widget only. */
export function parseKynoWidgetDetailed(
  raw: string,
  options?: { applyDefaults?: boolean },
): { ok: true; widget: KynoWidget } | { ok: false; failure: WidgetParseFailure } {
  const result = parseKynoWidgetBatchDetailed(raw, options)
  if (!result.ok) {
    return result
  }
  return { ok: true, widget: result.widgets[0]! }
}

export function parseKynoWidgetBatch(raw: string): KynoWidget[] {
  const result = parseKynoWidgetBatchDetailed(raw, { applyDefaults: true })
  if (result.ok) {
    return result.widgets
  }
  throw new Error(result.failure.message)
}

export function parseKynoWidget(raw: string): KynoWidget {
  const widgets = parseKynoWidgetBatch(raw)
  if (widgets.length === 0) {
    throw new Error('Assistant reply contained no widgets.')
  }
  return widgets[0]!
}

/**
 * Wrap a flat single-widget JSON string for Groq chat history so it matches the
 * batch schema the model must emit. Convex stores one flat widget per message.
 */
export function wrapWidgetContentForGroqHistory(content: string): string {
  const trimmed = content.trim()
  if (!trimmed.startsWith('{')) {
    return content
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return content
  }

  if (!isRecord(parsed)) {
    return content
  }

  if (Array.isArray(parsed.widgets)) {
    return content
  }

  if (typeof parsed.type !== 'string') {
    return content
  }

  const candidate = fillFlatWidgetDefaults(parsed)
  const flat = kynoWidgetFlatSchema.safeParse(candidate)
  if (!flat.success) {
    return content
  }

  return JSON.stringify({ widgets: [flat.data] })
}

export function serializeKynoWidget(widget: KynoWidget): string {
  if (widget.type === 'math') {
    return JSON.stringify({
      type: 'math',
      content: widget.latex,
      question: '',
      suggestedAnswers: [],
    })
  }

  if (widget.type === 'response') {
    return JSON.stringify({
      type: 'response',
      content: widget.content,
      question: '',
      suggestedAnswers: [],
    })
  }

  if (widget.type === 'question') {
    return JSON.stringify({
      type: 'question',
      content: '',
      question: widget.question,
      suggestedAnswers: widget.suggestedAnswers,
    })
  }

  return JSON.stringify({
    type: 'confirm',
    content: widget.content,
    question: widget.question,
    suggestedAnswers: widget.suggestedAnswers,
  })
}

export function serializeKynoWidgetBatch(widgets: KynoWidget[]): string {
  return JSON.stringify({ widgets: widgets.map((w) => JSON.parse(serializeKynoWidget(w))) })
}
