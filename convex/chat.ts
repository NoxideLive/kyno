import { ConvexError, v } from 'convex/values'
import { internal } from './_generated/api'
import { authedAction } from './auth/wrappers'
import { Permissions } from './auth/permissions'
import {
  type ChatDebugEvent,
  type GroqResponseMode,
  chatDebugEventValidator,
} from './chatDebug'
import { logGroq, systemPromptMeta, truncate } from './chatLogging'
import {
  classifyDomain,
  offTopicSuggestion,
  offTopicUserMessage,
  shouldBlockDomain,
} from './domain'
import {
  formatGroqUserMessageWithReplyContext,
  quoteTextFromContent,
} from './messageQuote'
import {
  KYNO_WIDGET_JSON_SCHEMA,
  parseKynoWidgetBatchDetailed,
  serializeKynoWidget,
  widgetRetryHint,
  wrapWidgetContentForGroqHistory,
  WIDGET_SYSTEM_PROMPT,
  type WidgetParseFailure,
} from './widgets'

const chatMessageValidator = v.object({
  role: v.union(v.literal('user'), v.literal('assistant'), v.literal('system')),
  content: v.string(),
})

export type { GroqResponseMode } from './chatDebug'

const DEFAULT_MODEL = 'openai/gpt-oss-20b'
const GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions'
const SCHEMA_NAME = 'kyno_widget'
const FAILED_GENERATION_SNIPPET_MAX = 1000
const MAX_WIDGET_ATTEMPTS = 3
const WIDGET_CORRECTION_PREFIX =
  '[Kyno validation — not shown to the user] Your previous widget JSON was invalid. Reply with exactly one corrected {"widgets":[...]} object.'

type GroqChatMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
}

type GroqErrorBody = {
  message?: string
  type?: string
  code?: string
  failed_generation?: string
}

type GroqChatCompletionResponse = {
  choices?: Array<{
    message?: {
      content?: string | null
    }
  }>
  usage?: {
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
  }
  error?: GroqErrorBody
}

type GroqFetchContext = {
  messageCount: number
  schemaName?: string
  systemPrompt?: string
}

type GroqErrorDetails = {
  groqMessage: string
  failedGeneration?: string
}

type GroqSchemaMismatchErrorData = {
  code: 'GROQ_SCHEMA_MISMATCH'
  message: string
  details?: GroqErrorDetails
}

function resolveModel(): string {
  return process.env.GROQ_MODEL?.trim() || DEFAULT_MODEL
}

function withWidgetSystemPrompt(messages: GroqChatMessage[]): GroqChatMessage[] {
  return [{ role: 'system', content: WIDGET_SYSTEM_PROMPT }, ...messages]
}

function groqHistoryMessage(message: GroqChatMessage): GroqChatMessage {
  if (message.role !== 'assistant') {
    return message
  }
  return {
    role: message.role,
    content: wrapWidgetContentForGroqHistory(message.content),
  }
}

function isSchemaMismatchMessage(message: string): boolean {
  return (
    message.includes('does not match the expected schema') ||
    message.includes('jsonschema') ||
    message.includes('failed_generation')
  )
}

function groqErrorFromPayload(
  payload: GroqChatCompletionResponse,
  status: number,
): { message: string; failedGeneration?: string; isSchemaMismatch: boolean } {
  const groqMessage = payload.error?.message ?? `Groq request failed (${status})`
  const failedGeneration = payload.error?.failed_generation
  return {
    message: groqMessage,
    failedGeneration,
    isSchemaMismatch: isSchemaMismatchMessage(groqMessage),
  }
}

function throwGroqRequestFailed(
  status: number,
  payload: GroqChatCompletionResponse,
): never {
  const { message, failedGeneration, isSchemaMismatch } = groqErrorFromPayload(payload, status)

  logGroq('response_failure', {
    status,
    code: isSchemaMismatch ? 'GROQ_SCHEMA_MISMATCH' : 'GROQ_REQUEST_FAILED',
    groqMessage: message,
    failedGeneration: failedGeneration ? truncate(failedGeneration, FAILED_GENERATION_SNIPPET_MAX) : undefined,
    errorType: payload.error?.type,
    errorCode: payload.error?.code,
  })

  if (isSchemaMismatch) {
    const details: GroqErrorDetails = {
      groqMessage: message,
      failedGeneration: failedGeneration
        ? truncate(failedGeneration, FAILED_GENERATION_SNIPPET_MAX)
        : undefined,
    }
    throw new ConvexError({
      code: 'GROQ_SCHEMA_MISMATCH',
      message: `Groq schema validation failed: ${truncate(message, 200)}`,
      details,
    })
  }

  throw new ConvexError({
    code: 'GROQ_REQUEST_FAILED',
    message,
    details: failedGeneration
      ? { groqMessage: message, failedGeneration: truncate(failedGeneration, FAILED_GENERATION_SNIPPET_MAX) }
      : undefined,
  })
}

function isGroqSchemaMismatchError(error: unknown): boolean {
  return (
    error instanceof ConvexError &&
    typeof error.data === 'object' &&
    error.data !== null &&
    (error.data as { code?: string }).code === 'GROQ_SCHEMA_MISMATCH'
  )
}

function groqDetailsFromSchemaMismatchError(
  error: ConvexError<GroqSchemaMismatchErrorData>,
): GroqErrorDetails {
  const data = error.data
  const groqMessage =
    data.details?.groqMessage?.trim() ||
    data.message.trim() ||
    'Groq schema validation failed.'
  const failedGeneration = data.details?.failedGeneration
  return { groqMessage, failedGeneration }
}

async function fetchGroqCompletion(
  apiKey: string,
  model: string,
  messages: GroqChatMessage[],
  mode: GroqResponseMode,
  context?: GroqFetchContext,
): Promise<string> {
  const systemPrompt = context?.systemPrompt ?? messages.find((m) => m.role === 'system')?.content
  const startedAt = Date.now()

  logGroq('request', {
    model,
    mode,
    messageCount: context?.messageCount ?? messages.length,
    schemaName: mode === 'json' ? (context?.schemaName ?? SCHEMA_NAME) : undefined,
    systemPrompt: systemPromptMeta(systemPrompt),
  })

  const body: Record<string, unknown> = {
    model,
    messages,
    stream: false,
  }

  if (mode === 'json') {
    body.response_format = {
      type: 'json_schema',
      json_schema: {
        name: SCHEMA_NAME,
        strict: true,
        schema: KYNO_WIDGET_JSON_SCHEMA,
      },
    }
  } else if (mode === 'json_object') {
    body.response_format = { type: 'json_object' }
  }

  const response = await fetch(GROQ_CHAT_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  const payload = (await response.json()) as GroqChatCompletionResponse
  const latencyMs = Date.now() - startedAt

  if (!response.ok) {
    throwGroqRequestFailed(response.status, payload)
  }

  const content = payload.choices?.[0]?.message?.content?.trim()
  if (!content) {
    logGroq('response_failure', {
      latencyMs,
      code: 'GROQ_EMPTY_RESPONSE',
      usage: payload.usage,
    })
    throw new ConvexError({
      code: 'GROQ_EMPTY_RESPONSE',
      message: 'No reply from the assistant.',
    })
  }

  logGroq('response_success', {
    mode,
    latencyMs,
    usage: payload.usage,
    contentLength: content.length,
  })

  return content
}

function logValidationFailure(
  raw: string,
  reason: string,
  zodIssues?: unknown,
): void {
  logGroq('validation_failure', {
    reason,
    rawContent: truncate(raw),
    rawLength: raw.length,
    zodIssues,
  })
}

function pushDebugEvent(debugTrace: ChatDebugEvent[] | undefined, event: ChatDebugEvent): void {
  debugTrace?.push(event)
}

function parseWidgetBatchWithDebug(
  raw: string,
  debugTrace: ChatDebugEvent[] | undefined,
  attempt: number,
): string[] | null {
  const result = parseKynoWidgetBatchDetailed(raw, { applyDefaults: true })
  if (result.ok) {
    logGroq('validation_success', {
      widgetCount: result.widgets.length,
      widgetTypes: result.widgets.map((widget) => widget.type),
    })
    return result.widgets.map((widget) => serializeKynoWidget(widget))
  }

  logValidationFailure(raw, result.failure.stage, result.failure.zodIssues)
  pushDebugEvent(debugTrace, {
    type: 'validation_failure',
    attempt,
    stage: result.failure.stage,
    message: result.failure.message,
    widgetIndex: result.failure.widgetIndex,
    rawSnippet: truncate(raw, FAILED_GENERATION_SNIPPET_MAX),
  })
  return null
}

function buildWidgetCorrectionMessage(
  failure: WidgetParseFailure,
  rejectedOutput?: string,
): string {
  const lines = [WIDGET_CORRECTION_PREFIX, '', widgetRetryHint(failure)]

  const snippet = rejectedOutput?.trim() || failure.raw?.trim() || ''
  if (snippet) {
    lines.push('', `Rejected output:\n${truncate(snippet, FAILED_GENERATION_SNIPPET_MAX)}`)
  }

  return lines.join('\n')
}

/**
 * Retry loop for Groq widget generation. `groqMessages` may grow with synthetic
 * assistant/user turns carrying validation feedback. That thread is ephemeral —
 * only the final validated widgets are returned and persisted for the user.
 */
async function fetchWidgetReply(
  apiKey: string,
  model: string,
  messages: GroqChatMessage[],
  debugTrace?: ChatDebugEvent[],
): Promise<string[]> {
  let groqMessages = withWidgetSystemPrompt(messages)
  let lastRaw = ''
  let lastFailureMessage = 'Assistant reply did not match the widget schema.'

  for (let attempt = 1; attempt <= MAX_WIDGET_ATTEMPTS; attempt++) {
    const mode: GroqResponseMode = attempt === 1 ? 'json' : 'json_object'
    pushDebugEvent(debugTrace, { type: 'attempt', attempt, mode })

    const context: GroqFetchContext = {
      messageCount: groqMessages.length,
      schemaName: SCHEMA_NAME,
      systemPrompt: WIDGET_SYSTEM_PROMPT,
    }

    try {
      const raw = await fetchGroqCompletion(apiKey, model, groqMessages, mode, context)
      lastRaw = raw
      const parsed = parseWidgetBatchWithDebug(raw, debugTrace, attempt)
      if (parsed) {
        const detail = parseKynoWidgetBatchDetailed(raw, { applyDefaults: true })
        if (detail.ok) {
          pushDebugEvent(debugTrace, {
            type: 'success',
            attempt,
            mode,
            widgetCount: detail.widgets.length,
            widgetTypes: detail.widgets.map((widget) => widget.type),
          })
        }
        return parsed
      }

      const failure = parseKynoWidgetBatchDetailed(raw, { applyDefaults: true })
      if (failure.ok) {
        break
      }

      lastFailureMessage = failure.failure.message

      if (attempt >= MAX_WIDGET_ATTEMPTS) {
        break
      }

      const correction = buildWidgetCorrectionMessage(failure.failure, raw)

      logGroq('retry', {
        attempt: attempt + 1,
        reason: 'local_validation_failed',
        message: failure.failure.message,
        widgetIndex: failure.failure.widgetIndex,
        correctionPreview: truncate(correction, 300),
      })

      pushDebugEvent(debugTrace, {
        type: 'retry_correction',
        attempt,
        correction,
      })

      groqMessages = [
        ...groqMessages,
        groqHistoryMessage({ role: 'assistant', content: raw }),
        {
          role: 'user',
          content: correction,
        },
      ]
    } catch (error) {
      if (isGroqSchemaMismatchError(error)) {
        const schemaError = error as ConvexError<GroqSchemaMismatchErrorData>
        const { groqMessage, failedGeneration } = groqDetailsFromSchemaMismatchError(schemaError)
        pushDebugEvent(debugTrace, {
          type: 'groq_error',
          attempt,
          groqMessage,
          failedGeneration,
        })
      }

      if (!isGroqSchemaMismatchError(error) || attempt >= MAX_WIDGET_ATTEMPTS) {
        throw error
      }

      const schemaError = error as ConvexError<GroqSchemaMismatchErrorData>
      const { groqMessage, failedGeneration } = groqDetailsFromSchemaMismatchError(schemaError)
      lastFailureMessage = groqMessage

      const schemaFailure: WidgetParseFailure = {
        stage: 'batch',
        message: groqMessage,
        raw: failedGeneration ?? '',
      }

      const correction = buildWidgetCorrectionMessage(schemaFailure, failedGeneration)

      logGroq('retry', {
        attempt: attempt + 1,
        reason: 'groq_schema_mismatch',
        groqMessage,
        failedGeneration,
        correctionPreview: truncate(correction, 300),
      })

      pushDebugEvent(debugTrace, {
        type: 'retry_correction',
        attempt,
        correction,
      })

      groqMessages = [
        ...groqMessages,
        ...(failedGeneration
          ? [groqHistoryMessage({ role: 'assistant', content: failedGeneration })]
          : []),
        {
          role: 'user',
          content: correction,
        },
      ]
    }
  }

  pushDebugEvent(debugTrace, {
    type: 'final_failure',
    message: lastFailureMessage,
    rawSnippet: truncate(lastRaw, FAILED_GENERATION_SNIPPET_MAX),
  })

  throw new ConvexError({
    code: 'GROQ_INVALID_WIDGET',
    message: lastFailureMessage,
    details: {
      rawSnippet: truncate(lastRaw, FAILED_GENERATION_SNIPPET_MAX),
      ...(debugTrace ? { debugTrace } : {}),
    },
  })
}

function attachDebugTraceToError(error: unknown, debugTrace: ChatDebugEvent[]): never {
  if (error instanceof ConvexError && typeof error.data === 'object' && error.data !== null) {
    const data = error.data as Record<string, unknown>
    throw new ConvexError({
      ...data,
      details: {
        ...(typeof data.details === 'object' && data.details !== null
          ? (data.details as Record<string, unknown>)
          : {}),
        debugTrace,
      },
    })
  }
  throw error
}

export const sendMessage = authedAction(Permissions.readProfile, {
  args: {
    messages: v.array(chatMessageValidator),
    conversationId: v.optional(v.id('conversations')),
    replyToMessageId: v.optional(v.id('messages')),
    mode: v.optional(v.union(v.literal('text'), v.literal('json'))),
    debug: v.optional(v.boolean()),
  },
  returns: v.object({
    messages: v.array(
      v.object({
        content: v.string(),
        contentFormat: v.optional(v.union(v.literal('widget'), v.literal('text'))),
      }),
    ),
    model: v.string(),
    debugTrace: v.optional(v.array(chatDebugEventValidator)),
  }),
  handler: async (ctx, args) => {
    const apiKey = process.env.GROQ_API_KEY?.trim()
    if (!apiKey) {
      throw new ConvexError({
        code: 'GROQ_NOT_CONFIGURED',
        message: 'Chat is not configured. Set GROQ_API_KEY in Convex.',
      })
    }

    if (args.messages.length === 0) {
      throw new ConvexError({
        code: 'INVALID_INPUT',
        message: 'At least one message is required.',
      })
    }

    const lastUserMessage = args.messages.at(-1)
    if (!lastUserMessage || lastUserMessage.role !== 'user') {
      throw new ConvexError({
        code: 'INVALID_INPUT',
        message: 'Last message must be from the user.',
      })
    }

    const domainResult = await classifyDomain(lastUserMessage.content)
    if (domainResult.ok && shouldBlockDomain(domainResult.classification)) {
      throw new ConvexError({
        code: 'OFF_TOPIC',
        message: offTopicUserMessage(),
        suggestion: offTopicSuggestion(),
      })
    }

    let replyQuote:
      | {
          role: 'user' | 'assistant'
          text: string
          truncated: boolean
          threadPosition?: number
          threadLength?: number
        }
      | undefined

    if (args.replyToMessageId && args.conversationId) {
      const replyTarget = await ctx.runQuery(internal.conversations.getMessageForReply, {
        conversationId: args.conversationId,
        messageId: args.replyToMessageId,
        userId: ctx.appAuth.userId,
      })
      if (replyTarget) {
        const quoted = quoteTextFromContent(
          replyTarget.content,
          replyTarget.role,
          replyTarget.contentFormat,
        )
        replyQuote = {
          role: replyTarget.role,
          text: quoted.text,
          truncated: quoted.truncated,
          threadPosition: replyTarget.threadPosition,
          threadLength: replyTarget.threadLength,
        }
      }
    }

    const mode: GroqResponseMode = args.mode ?? 'json'
    const model = resolveModel()
    const collectDebug = args.debug === true
    const debugTrace: ChatDebugEvent[] | undefined = collectDebug ? [] : undefined

    const groqMessages: GroqChatMessage[] = args.messages.map((message, index) => {
      const isLastUser =
        index === args.messages.length - 1 && message.role === 'user'
      const content =
        isLastUser && replyQuote
          ? formatGroqUserMessageWithReplyContext(message.content, replyQuote)
          : message.content

      return groqHistoryMessage({
        role: message.role,
        content,
      })
    })
    // User-visible history only — validation retry turns are added inside fetchWidgetReply.

    logGroq('send_message', {
      model,
      mode,
      messageCount: groqMessages.length,
      hasConversationId: Boolean(args.conversationId),
      debug: collectDebug,
    })

    pushDebugEvent(debugTrace, {
      type: 'send_start',
      model,
      mode,
      messageCount: groqMessages.length,
    })

    let assistantMessages: string[]
    try {
      assistantMessages =
        mode === 'json'
          ? await fetchWidgetReply(apiKey, model, groqMessages, debugTrace)
          : [
              await fetchGroqCompletion(apiKey, model, groqMessages, 'text', {
                messageCount: groqMessages.length,
              }),
            ]
    } catch (error) {
      if (debugTrace) {
        attachDebugTraceToError(error, debugTrace)
      }
      throw error
    }

    if (mode === 'text' && debugTrace) {
      pushDebugEvent(debugTrace, {
        type: 'success',
        attempt: 1,
        mode: 'text',
        widgetCount: 0,
        widgetTypes: [],
      })
    }

    const contentFormat = mode === 'json' ? ('widget' as const) : ('text' as const)

    if (args.conversationId) {
      await ctx.runMutation(internal.conversations.persistExchange, {
        userId: ctx.appAuth.userId,
        conversationId: args.conversationId,
        userContent: lastUserMessage.content,
        replyToMessageId: args.replyToMessageId,
        assistantMessages: assistantMessages.map((content) => ({
          content,
          contentFormat,
        })),
      })
    }

    return {
      messages: assistantMessages.map((content) => ({ content, contentFormat })),
      model,
      ...(debugTrace ? { debugTrace } : {}),
    }
  },
})
