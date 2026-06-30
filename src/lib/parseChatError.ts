import { ConvexError } from 'convex/values'
import type { ChatDebugEvent } from '@/lib/chatDebug'

export type ConvexErrorPayload = {
  code?: string
  message?: string
  suggestion?: string
  details?: {
    groqMessage?: string
    failedGeneration?: string
    rawSnippet?: string
    debugTrace?: ChatDebugEvent[]
  }
}

export type ParsedChatError =
  | { kind: 'off_topic'; message: string; suggestion?: string }
  | { kind: 'generic'; message: string; debugTrace?: ChatDebugEvent[] }

export function parseChatError(error: unknown): ParsedChatError {
  if (error instanceof ConvexError) {
    const data = error.data as ConvexErrorPayload
    if (data?.code === 'OFF_TOPIC') {
      return {
        kind: 'off_topic',
        message: data.message ?? 'That question is outside CAPS Mathematics.',
        suggestion: data.suggestion,
      }
    }
    if (typeof data?.message === 'string') {
      const message = data.message
      const debugTrace = data.details?.debugTrace
      return { kind: 'generic', message, ...(debugTrace ? { debugTrace } : {}) }
    }
  }

  if (error instanceof Error) {
    return { kind: 'generic', message: error.message }
  }

  return { kind: 'generic', message: 'Could not get a reply. Try again.' }
}
