import { ref, watch, type Ref } from 'vue'
import { useConvexClient, useConvexMutation } from 'convex-vue'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'
import { useConvexAuthPending } from '@/composables/useConvexAuthReady'
import {
  applyStoredDebugTraces,
  clearFailedDebugTrace,
  getFailedDebugTrace,
  setFailedDebugTrace,
  setMessageDebugTrace,
  type ChatDebugEvent,
} from '@/lib/chatDebug'
import { prepareMessageContent } from '@/lib/messageContent'
import { parseChatError } from '@/lib/parseChatError'

export type ChatRole = 'user' | 'assistant'

export type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  contentFormat?: 'widget' | 'text'
  replyToMessageId?: Id<'messages'>
  debugTrace?: ChatDebugEvent[]
  /** Client-only: blocked off-topic attempt — visible until the next send. */
  ephemeral?: boolean
}

export type SendMessageOptions = {
  replyToMessageId?: Id<'messages'>
}

export type FailedChatDebug = {
  events: ChatDebugEvent[]
  errorMessage: string
}

export type UseGroqChatReturn = {
  messages: Ref<ChatMessage[]>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  offTopicHint: Ref<string | null>
  failedDebug: Ref<FailedChatDebug | null>
  send: (content: string, options?: SendMessageOptions) => Promise<Id<'conversations'> | null>
  clearError: () => void
  reset: () => void
}

function messageFromDoc(doc: {
  _id: Id<'messages'>
  role: ChatRole
  content: string
  contentFormat?: 'widget' | 'text'
  replyToMessageId?: Id<'messages'>
}): ChatMessage {
  return {
    id: doc._id,
    role: doc.role,
    content: doc.content,
    contentFormat: doc.contentFormat,
    replyToMessageId: doc.replyToMessageId,
  }
}

export function useGroqChat(
  conversationId: Ref<Id<'conversations'> | null>,
  onConversationCreated?: (id: Id<'conversations'>) => void,
  debugEnabled?: Ref<boolean>,
): UseGroqChatReturn {
  const client = useConvexClient()
  const convexPending = useConvexAuthPending()
  const { mutate: createConversation } = useConvexMutation(api.conversations.create)

  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const offTopicHint = ref<string | null>(null)
  const failedDebug = ref<FailedChatDebug | null>(null)
  const pendingConversationId = ref<Id<'conversations'> | null>(null)

  function hydrateMessages(
    id: Id<'conversations'>,
    docs: Parameters<typeof messageFromDoc>[0][],
  ): ChatMessage[] {
    return applyStoredDebugTraces(id, docs.map(messageFromDoc))
  }

  watch(
    [conversationId, convexPending],
    async ([id, pending]) => {
      pendingConversationId.value = null
      if (pending || !id) {
        if (!pending && !isLoading.value) {
          messages.value = []
          failedDebug.value = null
        }
        return
      }

      try {
        const data = await client.query(api.conversations.get, {
          conversationId: id,
        })
        if (conversationId.value !== id) return
        messages.value = hydrateMessages(id, data.messages)
        failedDebug.value = getFailedDebugTrace(id)
      } catch (e) {
        if (conversationId.value !== id) return
        const message =
          e instanceof Error ? e.message : 'Could not load conversation.'
        error.value = message
        messages.value = []
        failedDebug.value = null
      }
    },
    { immediate: true },
  )

  function attachDebugTraceToLastAssistant(
    id: Id<'conversations'>,
    trace: ChatDebugEvent[],
  ): void {
    const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
    if (!lastAssistant) return
    lastAssistant.debugTrace = trace
    setMessageDebugTrace(id, lastAssistant.id, trace)
  }

  async function send(
    content: string,
    options?: SendMessageOptions,
  ): Promise<Id<'conversations'> | null> {
    const trimmed = content.trim()
    if (!trimmed || isLoading.value) return null

    const replyToMessageId = options?.replyToMessageId

    const conversationIdForSend: Id<'conversations'> = await (async () => {
      const existing = conversationId.value ?? pendingConversationId.value
      if (existing) return existing

      const createdId = await createConversation({})
      if (!createdId) {
        throw new Error('Could not start a conversation.')
      }

      pendingConversationId.value = createdId
      onConversationCreated?.(createdId)
      return createdId
    })()

    const preparedContent = prepareMessageContent(trimmed)

    messages.value = messages.value.filter((message) => !message.ephemeral)

    const optimisticId = crypto.randomUUID()
    messages.value.push({
      id: optimisticId,
      role: 'user',
      content: preparedContent,
      replyToMessageId,
    })

    isLoading.value = true
    error.value = null
    offTopicHint.value = null
    failedDebug.value = null
    clearFailedDebugTrace(conversationIdForSend)

    const collectDebug = debugEnabled?.value === true

    try {
      const payload = messages.value
        .filter((message) => !message.ephemeral)
        .map((message) => ({
          role: message.role,
          content: message.content,
        }))

      const result = await client.action(api.chat.sendMessage, {
        messages: payload,
        conversationId: conversationIdForSend,
        ...(replyToMessageId ? { replyToMessageId } : {}),
        mode: 'json',
        ...(collectDebug ? { debug: true } : {}),
      })

      const debugTrace = collectDebug ? result.debugTrace : undefined

      messages.value.push({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: result.messages[0]?.content ?? '',
        contentFormat: result.messages[0]?.contentFormat,
        debugTrace,
      })

      const data = await client.query(api.conversations.get, {
        conversationId: conversationIdForSend,
      })
      messages.value = hydrateMessages(conversationIdForSend, data.messages)
      if (debugTrace && debugTrace.length > 0) {
        attachDebugTraceToLastAssistant(conversationIdForSend, debugTrace)
      }

      return conversationIdForSend
    } catch (e) {
      const parsed = parseChatError(e)
      if (parsed.kind === 'off_topic') {
        messages.value = messages.value.map((message) =>
          message.id === optimisticId ? { ...message, ephemeral: true } : message,
        )
        offTopicHint.value = parsed.suggestion
          ? `${parsed.message} ${parsed.suggestion}`
          : parsed.message
      } else {
        messages.value = messages.value.filter((message) => message.id !== optimisticId)
        error.value = parsed.message
        if (collectDebug && parsed.kind === 'generic' && parsed.debugTrace) {
          const failed = {
            events: parsed.debugTrace,
            errorMessage: parsed.message,
          }
          failedDebug.value = failed
          setFailedDebugTrace(conversationIdForSend, failed)
        }
      }
      return conversationIdForSend
    } finally {
      isLoading.value = false
    }
  }

  function clearError(): void {
    error.value = null
    offTopicHint.value = null
    const id = conversationId.value ?? pendingConversationId.value
    if (id) clearFailedDebugTrace(id)
    failedDebug.value = null
  }

  function reset(): void {
    pendingConversationId.value = null
    messages.value = []
    error.value = null
    offTopicHint.value = null
    failedDebug.value = null
  }

  return { messages, isLoading, error, offTopicHint, failedDebug, send, clearError, reset }
}
