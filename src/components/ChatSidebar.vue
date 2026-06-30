<script setup lang="ts">
import { computed } from 'vue'
import { useConvexMutation } from 'convex-vue'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'
import { useConvexAuthPending, useConvexAuthReady } from '@/composables/useConvexAuthReady'
import { useOptionalConvexQuery } from '@/composables/useOptionalConvexQuery'

const props = defineProps<{
  activeId: Id<'conversations'> | null
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  newChat: []
  select: [id: Id<'conversations'>]
}>()

const convexReady = useConvexAuthReady()
const convexPending = useConvexAuthPending()

const { data: conversations, isPending } = useOptionalConvexQuery(
  api.conversations.list,
  () => (convexReady.value ? {} : 'skip'),
)

const { mutate: removeConversation } = useConvexMutation(api.conversations.remove)

const items = computed(() => conversations.value ?? [])

function formatDate(timestamp: number): string {
  const date = new Date(timestamp)
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  if (sameDay) {
    return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  }

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function displayTitle(title: string | undefined): string {
  return title?.trim() || 'New chat'
}

async function onDelete(id: Id<'conversations'>): Promise<void> {
  await removeConversation({ conversationId: id })
  if (props.activeId === id) emit('newChat')
}

function onDeleteClick(event: MouseEvent, id: Id<'conversations'>): void {
  event.preventDefault()
  event.stopPropagation()
  void onDelete(id)
}

function onDeleteKeydown(event: KeyboardEvent, id: Id<'conversations'>): void {
  event.preventDefault()
  event.stopPropagation()
  void onDelete(id)
}

function onSelect(id: Id<'conversations'>): void {
  emit('select', id)
  emit('close')
}
</script>

<template>
  <aside
    class="sidebar"
    :class="{ open }"
    aria-label="Conversations"
  >
    <div class="sidebar-inner">
      <header class="sidebar-header">
        <button type="button" class="new-chat" @click="emit('newChat')">
          New chat
        </button>
        <button
          type="button"
          class="close-drawer"
          aria-label="Close sidebar"
          @click="emit('close')"
        >
          ×
        </button>
      </header>

      <nav class="conversation-list" aria-label="Past conversations">
        <p v-if="convexPending" class="status">Connecting…</p>
        <p v-else-if="isPending" class="status">Loading…</p>
        <p v-else-if="items.length === 0" class="status">No conversations yet.</p>

        <button
          v-for="conversation in items"
          :key="conversation._id"
          type="button"
          class="conversation-item"
          :class="{ active: conversation._id === activeId }"
          @click="onSelect(conversation._id)"
        >
          <span class="conversation-title">{{ displayTitle(conversation.title) }}</span>
          <span class="conversation-meta">
            <time :datetime="new Date(conversation.updatedAt).toISOString()">
              {{ formatDate(conversation.updatedAt) }}
            </time>
            <span
              role="button"
              tabindex="0"
              class="delete"
              aria-label="Delete conversation"
              @click="onDeleteClick($event, conversation._id)"
              @keydown.enter.prevent="onDeleteKeydown($event, conversation._id)"
            >
              Delete
            </span>
          </span>
        </button>
      </nav>
    </div>
  </aside>

  <button
    v-if="open"
    type="button"
    class="backdrop"
    aria-label="Close sidebar"
    @click="emit('close')"
  />
</template>

<style scoped>
.sidebar {
  flex-shrink: 0;
  width: 16rem;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--border);
  background: var(--surface);
}

.sidebar-inner {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.sidebar-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-bottom: 1px solid var(--border);
}

.new-chat {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--bg);
  color: var(--text);
  font-size: 0.875rem;
  font-weight: 500;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  text-align: left;
}

.new-chat:hover {
  background: var(--accent-muted);
  border-color: var(--accent);
}

.close-drawer {
  display: none;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 1.5rem;
  line-height: 1;
  padding: 0.25rem 0.5rem;
  cursor: pointer;
}

.conversation-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.status {
  margin: 0.5rem;
  color: var(--muted);
  font-size: 0.8125rem;
}

.conversation-item {
  width: 100%;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--text);
  text-align: left;
  padding: 0.5rem 0.625rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.conversation-item:hover {
  background: var(--bg);
}

.conversation-item.active {
  background: var(--accent-muted);
}

.conversation-title {
  font-size: 0.875rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--muted);
}

.delete {
  opacity: 0;
  font-size: 0.6875rem;
  color: #b91c1c;
  cursor: pointer;
}

.conversation-item:hover .delete,
.conversation-item:focus-within .delete {
  opacity: 1;
}

.delete:hover {
  text-decoration: underline;
}

.backdrop {
  display: none;
}

@media (min-width: 769px) {
  .sidebar {
    transform: none;
  }
}

@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 40;
    width: min(16rem, 85vw);
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    box-shadow: none;
  }

  .sidebar.open {
    transform: translateX(0);
    box-shadow: 0.25rem 0 1.5rem rgb(15 23 42 / 0.12);
  }

  .close-drawer {
    display: block;
  }

  .backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 30;
    border: none;
    background: rgb(15 23 42 / 0.35);
    cursor: pointer;
  }
}
</style>
