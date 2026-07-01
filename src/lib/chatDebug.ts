export type { ChatDebugEvent, GroqResponseMode } from '../../convex/chatDebug'
import type { ChatDebugEvent } from '../../convex/chatDebug'

export const CHAT_DEBUG_STORAGE_KEY = 'kyno:chat-debug'
export const CHAT_DEBUG_TRACES_STORAGE_KEY = 'kyno:chat-debug-traces'

export type StoredFailedDebug = {
  events: ChatDebugEvent[]
  errorMessage: string
}

type ConversationDebugStore = {
  messages: Record<string, ChatDebugEvent[]>
  failed?: StoredFailedDebug
}

type DebugTraceStore = Record<string, ConversationDebugStore>

function isDev(): boolean {
  return import.meta.env.DEV
}

function readStore(): DebugTraceStore {
  if (!isDev()) return {}
  try {
    const raw = sessionStorage.getItem(CHAT_DEBUG_TRACES_STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw) as DebugTraceStore
  } catch {
    return {}
  }
}

function writeStore(store: DebugTraceStore): void {
  if (!isDev()) return
  try {
    sessionStorage.setItem(CHAT_DEBUG_TRACES_STORAGE_KEY, JSON.stringify(store))
  } catch {
    // sessionStorage may be unavailable
  }
}

function conversationStore(
  store: DebugTraceStore,
  conversationId: string,
): ConversationDebugStore {
  return store[conversationId] ?? { messages: {} }
}

export function getMessageDebugTrace(
  conversationId: string,
  messageId: string,
): ChatDebugEvent[] | undefined {
  const traces = conversationStore(readStore(), conversationId).messages[messageId]
  return traces && traces.length > 0 ? traces : undefined
}

export function setMessageDebugTrace(
  conversationId: string,
  messageId: string,
  trace: ChatDebugEvent[],
): void {
  if (!isDev() || trace.length === 0) return
  const store = readStore()
  const entry = conversationStore(store, conversationId)
  entry.messages[messageId] = trace
  store[conversationId] = entry
  writeStore(store)
}

export type MessageWithDebugTrace = {
  id: string
  role: string
  debugTrace?: ChatDebugEvent[]
}

export function applyStoredDebugTraces<T extends MessageWithDebugTrace>(
  conversationId: string,
  messages: T[],
): T[] {
  if (!isDev()) return messages
  const stored = conversationStore(readStore(), conversationId).messages
  if (Object.keys(stored).length === 0) return messages

  return messages.map((message) => {
    const trace = stored[message.id]
    if (!trace || trace.length === 0) return message
    return { ...message, debugTrace: trace }
  })
}

export function getFailedDebugTrace(conversationId: string): StoredFailedDebug | null {
  if (!isDev()) return null
  return conversationStore(readStore(), conversationId).failed ?? null
}

export function setFailedDebugTrace(
  conversationId: string,
  failed: StoredFailedDebug,
): void {
  if (!isDev() || failed.events.length === 0) return
  const store = readStore()
  const entry = conversationStore(store, conversationId)
  entry.failed = failed
  store[conversationId] = entry
  writeStore(store)
}

export function clearFailedDebugTrace(conversationId: string): void {
  if (!isDev()) return
  const store = readStore()
  const entry = store[conversationId]
  if (!entry?.failed) return
  delete entry.failed
  if (Object.keys(entry.messages).length === 0) {
    delete store[conversationId]
  } else {
    store[conversationId] = entry
  }
  writeStore(store)
}
