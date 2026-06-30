import { v } from 'convex/values'

export type GroqResponseMode = 'text' | 'json' | 'json_object'

export type ChatDebugEvent =
  | { type: 'send_start'; model: string; mode: GroqResponseMode; messageCount: number }
  | { type: 'attempt'; attempt: number; mode: GroqResponseMode }
  | {
      type: 'validation_failure'
      attempt: number
      stage: string
      message: string
      widgetIndex?: number
      rawSnippet?: string
    }
  | { type: 'retry_correction'; attempt: number; correction: string }
  | {
      type: 'groq_error'
      attempt: number
      groqMessage: string
      failedGeneration?: string
    }
  | {
      type: 'success'
      attempt: number
      mode: GroqResponseMode
      widgetCount: number
      widgetTypes: string[]
    }
  | { type: 'final_failure'; message: string; rawSnippet?: string }

const groqResponseModeValidator = v.union(
  v.literal('text'),
  v.literal('json'),
  v.literal('json_object'),
)

export const chatDebugEventValidator = v.union(
  v.object({
    type: v.literal('send_start'),
    model: v.string(),
    mode: groqResponseModeValidator,
    messageCount: v.number(),
  }),
  v.object({
    type: v.literal('attempt'),
    attempt: v.number(),
    mode: groqResponseModeValidator,
  }),
  v.object({
    type: v.literal('validation_failure'),
    attempt: v.number(),
    stage: v.string(),
    message: v.string(),
    widgetIndex: v.optional(v.number()),
    rawSnippet: v.optional(v.string()),
  }),
  v.object({
    type: v.literal('retry_correction'),
    attempt: v.number(),
    correction: v.string(),
  }),
  v.object({
    type: v.literal('groq_error'),
    attempt: v.number(),
    groqMessage: v.string(),
    failedGeneration: v.optional(v.string()),
  }),
  v.object({
    type: v.literal('success'),
    attempt: v.number(),
    mode: groqResponseModeValidator,
    widgetCount: v.number(),
    widgetTypes: v.array(v.string()),
  }),
  v.object({
    type: v.literal('final_failure'),
    message: v.string(),
    rawSnippet: v.optional(v.string()),
  }),
)
