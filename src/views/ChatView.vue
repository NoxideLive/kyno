<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowUturnLeftIcon, ExclamationCircleIcon, XMarkIcon } from '@heroicons/vue/24/solid'
import AppNav from '@/components/AppNav.vue'
import ChatDebugPanel from '@/components/ChatDebugPanel.vue'
import ChatMessageContent from '@/components/ChatMessageContent.vue'
import ChatQuotePreview from '@/components/ChatQuotePreview.vue'
import ChatSidebar from '@/components/ChatSidebar.vue'
import { useChatDebugMode } from '@/composables/useChatDebugMode'
import { useConvexAuthReady } from '@/composables/useConvexAuthReady'
import { useGroqChat, type ChatMessage } from '@/composables/useGroqChat'
import { isInteractiveWidget, parseWidgetContent } from '@/lib/widgets'
import {
  isPersistedMessageId,
  quotePreviewFromMessage,
  type QuotePreview,
} from '@/lib/messageQuote'
import type { Id } from '../../convex/_generated/dataModel'

type PendingQuote = QuotePreview & {
  messageId: string
}

const route = useRoute()
const router = useRouter()
const convexReady = useConvexAuthReady()

const sidebarOpen = ref(false)

const conversationId = computed<Id<'conversations'> | null>(() => {
  const param = route.params.conversationId
  if (typeof param !== 'string' || !param) return null
  return param as Id<'conversations'>
})

function navigateToConversation(id: Id<'conversations'> | null): void {
  if (id) {
    void router.push({ name: 'chat', params: { conversationId: id } })
    return
  }
  void router.push({ name: 'chat' })
}

const { debugEnabled, showToggle, toggleDebug } = useChatDebugMode()

const { messages, isLoading, error, offTopicHint, failedDebug, send, clearError, reset } =
  useGroqChat(conversationId, (id) => navigateToConversation(id), debugEnabled)

const draft = ref('')
const messageListRef = ref<HTMLElement | null>(null)
const pendingQuote = ref<PendingQuote | null>(null)
const composerRef = ref<HTMLTextAreaElement | null>(null)

async function scrollToBottom(): Promise<void> {
  await nextTick()
  const list = messageListRef.value
  if (!list) return
  list.scrollTop = list.scrollHeight
}

watch(
  messages,
  () => {
    void scrollToBottom()
  },
  { deep: true },
)

watch(isLoading, (loading) => {
  if (loading) void scrollToBottom()
})

onMounted(() => {
  void scrollToBottom()
})

async function onSelectAnswer(answer: string): Promise<void> {
  if (!convexReady.value || isLoading.value) return
  await send(answer)
}

async function onSubmit(): Promise<void> {
  if (!convexReady.value || isLoading.value) return

  const text = draft.value
  draft.value = ''

  const replyToMessageId =
    pendingQuote.value && isPersistedMessageId(pendingQuote.value.messageId)
      ? (pendingQuote.value.messageId as Id<'messages'>)
      : undefined

  pendingQuote.value = null

  await send(text, replyToMessageId ? { replyToMessageId } : undefined)
}

function quoteMessage(message: ChatMessage): void {
  pendingQuote.value = {
    messageId: message.id,
    ...quotePreviewFromMessage(message),
  }
  void nextTick(() => composerRef.value?.focus())
}

function clearQuote(): void {
  pendingQuote.value = null
}

function quotedMessageFor(message: ChatMessage): ChatMessage | null {
  if (!message.replyToMessageId) return null
  return (
    messages.value.find((candidate) => candidate.id === message.replyToMessageId) ??
    null
  )
}

function quotePreviewFor(message: ChatMessage): PendingQuote | null {
  const target = quotedMessageFor(message)
  if (!target) return null
  return {
    messageId: target.id,
    ...quotePreviewFromMessage(target),
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  void onSubmit()
}

function onNewChat(): void {
  reset()
  pendingQuote.value = null
  navigateToConversation(null)
  sidebarOpen.value = false
}

function onSelectConversation(id: Id<'conversations'>): void {
  navigateToConversation(id)
}

function toggleSidebar(): void {
  sidebarOpen.value = !sidebarOpen.value
}

function widgetSelectedAnswer(message: ChatMessage, index: number): string | null {
  if (message.role !== 'assistant' || message.contentFormat !== 'widget') return null
  const widget = parseWidgetContent(message.content, message.contentFormat)
  if (!widget || !isInteractiveWidget(widget)) return null

  for (let i = index + 1; i < messages.value.length; i++) {
    const next = messages.value[i]
    if (!next) continue
    if (next.role === 'user') return next.content
  }

  return null
}
</script>

<template>
  <div class="page">
    <AppNav />
    <div class="shell">
      <ChatSidebar
        :active-id="conversationId"
        :open="sidebarOpen"
        @close="sidebarOpen = false"
        @new-chat="onNewChat"
        @select="onSelectConversation"
      />

      <main class="main">
        <header class="chat-header">
          <button
            type="button"
            class="menu-toggle"
            aria-label="Open conversations"
            @click="toggleSidebar"
          >
            ☰
          </button>
          <h1 class="chat-title">Chat</h1>
          <button
            v-if="showToggle"
            type="button"
            class="debug-toggle"
            :class="{ active: debugEnabled }"
            :aria-pressed="debugEnabled"
            @click="toggleDebug"
          >
            Debug
          </button>
        </header>

        <section class="chat" aria-label="Chat conversation">
          <div ref="messageListRef" class="messages" role="log" aria-live="polite">
            <p v-if="messages.length === 0" class="empty">Send a message to start.</p>

            <article
              v-for="(message, index) in messages"
              :key="message.id"
              class="message-row"
              :class="[message.role, { blocked: message.ephemeral }]"
              :aria-label="message.ephemeral ? 'Blocked: off topic' : undefined"
            >
              <div class="message-row__content">
                <div class="bubble">
                  <div v-if="!message.ephemeral" class="bubble-actions">
                    <button
                      type="button"
                      class="quote-action"
                      aria-label="Quote"
                      title="Quote"
                      @click="quoteMessage(message)"
                    >
                      <ArrowUturnLeftIcon class="quote-action__icon" aria-hidden="true" />
                    </button>
                  </div>
                  <div class="bubble-body" :class="{ 'bubble-body--blocked': message.ephemeral }">
                    <ExclamationCircleIcon
                      v-if="message.ephemeral"
                      class="blocked-icon"
                      aria-hidden="true"
                    />
                    <ChatQuotePreview
                    v-if="quotePreviewFor(message)"
                    align="right"
                    :role="quotePreviewFor(message)!.role"
                    :snippet="quotePreviewFor(message)!.snippet"
                    :kind="quotePreviewFor(message)!.kind"
                    :notation-latex="quotePreviewFor(message)!.notationLatex"
                  />
                  <ChatMessageContent
                    :content="message.content"
                    :content-format="message.contentFormat"
                    :selected-answer="widgetSelectedAnswer(message, index)"
                    @select-answer="onSelectAnswer"
                  />
                  </div>
                </div>
              </div>
              <ChatDebugPanel
                v-if="debugEnabled && message.role === 'assistant' && message.debugTrace"
                :events="message.debugTrace"
              />
            </article>

            <p v-if="isLoading" class="thinking">Thinking…</p>
          </div>

          <div class="footer">
            <p v-if="offTopicHint" class="off-topic" role="status">
              {{ offTopicHint }}
              <button type="button" class="hint-dismiss" @click="clearError">Dismiss</button>
            </p>

            <p v-if="error" class="error" role="alert">
              {{ error }}
              <button type="button" class="error-dismiss" @click="clearError">Dismiss</button>
            </p>

            <ChatDebugPanel
              v-if="debugEnabled && failedDebug"
              :events="failedDebug.events"
              :error-message="failedDebug.errorMessage"
              class="failed-debug"
            />

            <form class="composer" @submit.prevent="onSubmit">
              <div v-if="pendingQuote" class="composer-quote">
                <ChatQuotePreview
                  :role="pendingQuote.role"
                  :snippet="pendingQuote.snippet"
                  :kind="pendingQuote.kind"
                  :notation-latex="pendingQuote.notationLatex"
                  compact
                />
                <button
                  type="button"
                  class="composer-quote__dismiss"
                  aria-label="Remove quote"
                  @click="clearQuote"
                >
                  <XMarkIcon class="composer-quote__dismiss-icon" aria-hidden="true" />
                </button>
              </div>
              <div class="composer-row">
                <textarea
                  ref="composerRef"
                  v-model="draft"
                  class="input"
                  rows="2"
                  placeholder="Message"
                  :disabled="!convexReady || isLoading"
                  aria-label="Message"
                  @keydown="onKeydown"
                />
                <button
                  type="submit"
                  class="send"
                  :disabled="!convexReady || isLoading || !draft.trim()"
                >
                  Send
                </button>
              </div>
            </form>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.page {
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.shell {
  flex: 1;
  display: flex;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  padding: 0 1rem 1rem;
}

.chat-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

.menu-toggle {
  display: none;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--surface);
  color: var(--text);
  font-size: 1rem;
  line-height: 1;
  padding: 0.375rem 0.625rem;
  cursor: pointer;
}

.chat-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  flex: 1;
}

.debug-toggle {
  border: 1px dashed var(--border);
  border-radius: 0.375rem;
  background: transparent;
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.25rem 0.5rem;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.debug-toggle.active {
  border-style: solid;
  border-color: var(--accent-muted);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}

.failed-debug {
  margin: 0 0.75rem 0.5rem;
}

.chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  background: var(--surface);
  overflow: hidden;
}

.messages {
  flex: 1 1 0;
  min-height: 0;
  min-width: 0;
  overflow-x: clip;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.empty {
  margin: auto 0;
  text-align: center;
  color: var(--muted);
  font-size: 0.875rem;
}

.message-row {
  display: flex;
  flex-direction: column;
  min-width: 0;
  width: 100%;
}

.message-row__content {
  display: flex;
  min-width: 0;
}

.message-row.user .message-row__content {
  align-self: flex-end;
  max-width: 85%;
}

.message-row.assistant .message-row__content {
  align-self: flex-start;
  max-width: min(48rem, 85%);
}

.bubble {
  position: relative;
  min-width: 0;
  width: fit-content;
  max-width: 100%;
  margin: 0;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  font-size: 0.875rem;
  line-height: 1.45;
  word-break: break-word;
}

.bubble-actions {
  position: absolute;
  top: 0.375rem;
  right: 0.375rem;
  z-index: 1;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.message-row:hover .bubble-actions,
.message-row:focus-within .bubble-actions {
  opacity: 1;
  pointer-events: auto;
}

.bubble :deep(.quote-preview) {
  padding-right: 1.5rem;
}

.quote-action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  border-radius: 0.25rem;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  padding: 0;
}

.quote-action:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--text) 6%, transparent);
}

.message-row.user .quote-action {
  color: color-mix(in srgb, #fff 65%, transparent);
}

.message-row.user .quote-action:hover {
  color: #fff;
  background: color-mix(in srgb, #fff 15%, transparent);
}

.quote-action__icon {
  width: 0.875rem;
  height: 0.875rem;
}

.message-row.user .bubble {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 0.25rem;
}

.message-row.blocked .bubble {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
  border-bottom-right-radius: 0.25rem;
}

.bubble-body {
  min-width: 0;
}

.bubble-body--blocked {
  display: flex;
  align-items: flex-start;
  gap: 0.375rem;
}

.blocked-icon {
  flex-shrink: 0;
  width: 1.125rem;
  height: 1.125rem;
  margin-top: 0.1rem;
  color: #dc2626;
}

.message-row.assistant .bubble {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-bottom-left-radius: 0.25rem;
}

.thinking {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
  font-style: italic;
}

.footer {
  flex-shrink: 0;
  min-width: 0;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.error {
  margin: 0;
  padding: 0.5rem 1rem;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 0.875rem;
  border-bottom: 1px solid #fecaca;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.error-dismiss {
  border: none;
  background: transparent;
  color: #b91c1c;
  font-size: 0.8125rem;
  cursor: pointer;
  text-decoration: underline;
  flex-shrink: 0;
}

.off-topic {
  margin: 0;
  padding: 0.5rem 1rem;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 0.875rem;
  border-bottom: 1px solid #fecaca;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.hint-dismiss {
  border: none;
  background: transparent;
  color: #b91c1c;
  font-size: 0.8125rem;
  cursor: pointer;
  text-decoration: underline;
  flex-shrink: 0;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  min-width: 0;
}

.composer-quote {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--bg);
}

.composer-quote .quote-preview {
  flex: 1;
  min-width: 0;
}

.composer-quote__dismiss {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  border-radius: 0.25rem;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  padding: 0;
}

.composer-quote__dismiss:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--text) 6%, transparent);
}

.composer-quote__dismiss-icon {
  width: 0.875rem;
  height: 0.875rem;
}

.composer-row {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
  min-width: 0;
}

.input {
  flex: 1;
  min-width: 0;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  font-family: inherit;
  font-size: 0.875rem;
  line-height: 1.4;
  background: var(--bg);
  color: var(--text);
  max-height: 8rem;
  overflow-y: auto;
}

.input:focus {
  outline: 2px solid var(--accent-muted);
  border-color: var(--accent);
}

.input:disabled {
  opacity: 0.6;
}

.send {
  flex-shrink: 0;
  border: none;
  border-radius: 0.375rem;
  background: var(--accent);
  color: #fff;
  font-size: 0.875rem;
  font-weight: 500;
  padding: 0.5rem 1rem;
  cursor: pointer;
  white-space: nowrap;
}

.send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .menu-toggle {
    display: block;
  }

  .main {
    padding: 0 0.5rem 0.5rem;
  }

  .chat {
    border-radius: 0.375rem;
  }

  .messages {
    padding: 0.75rem;
  }

  .composer {
    padding: 0.5rem;
  }
}
</style>
