import { ref, watch, type Ref } from 'vue'
import { useConvexClient, useConvexMutation } from 'convex-vue'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'
import { useConvexAuthPending } from '@/composables/useConvexAuthReady'
import type { ChatDebugEvent } from '@/lib/chatDebug'
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
  const pendingDebugTrace = ref<ChatDebugEvent[] | null>(null)

  watch(
    [conversationId, convexPending],
    async ([id, pending]) => {
      pendingConversationId.value = null
      if (pending || !id) {
        if (!pending && !isLoading.value) messages.value = []
        return
      }

      try {
        const data = await client.query(api.conversations.get, {
          conversationId: id,
        })
        if (conversationId.value !== id) return
        messages.value = data.messages.map(messageFromDoc)
      } catch (e) {
        if (conversationId.value !== id) return
        const message =
          e instanceof Error ? e.message : 'Could not load conversation.'
        error.value = message
        messages.value = []
      }
    },
    { immediate: true },
  )

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

    const collectDebug = debugEnabled?.value === true

    try {
      const payload = messages.value.map((message) => ({
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

      if (collectDebug && result.debugTrace) {
        pendingDebugTrace.value = result.debugTrace
      }

      messages.value.push({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: result.messages[0]?.content ?? '',
        contentFormat: result.messages[0]?.contentFormat,
        debugTrace: collectDebug ? result.debugTrace : undefined,
      })

      const data = await client.query(api.conversations.get, {
        conversationId: conversationIdForSend,
      })
      messages.value = data.messages.map(messageFromDoc)
      if (pendingDebugTrace.value) {
        const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant')
        if (lastAssistant) {
          lastAssistant.debugTrace = pendingDebugTrace.value
        }
        pendingDebugTrace.value = null
      }

      return conversationIdForSend
    } catch (e) {
      const parsed = parseChatError(e)
      if (parsed.kind === 'off_topic') {
        // Keep user message visible; show domain redirect copy.
        offTopicHint.value = parsed.suggestion
          ? `${parsed.message} ${parsed.suggestion}`
          : parsed.message
      } else {
        messages.value = messages.value.filter((message) => message.id !== optimisticId)
        error.value = parsed.message
        if (collectDebug && parsed.kind === 'generic' && parsed.debugTrace) {
          failedDebug.value = {
            events: parsed.debugTrace,
            errorMessage: parsed.message,
          }
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
    failedDebug.value = null
  }

  function reset(): void {
    pendingConversationId.value = null
    messages.value = []
    error.value = null
    offTopicHint.value = null
    failedDebug.value = null
    pendingDebugTrace.value = null
  }

  return { messages, isLoading, error, offTopicHint, failedDebug, send, clearError, reset }
}
