import { ConvexError, v } from 'convex/values'
import { internal } from './_generated/api'
import { internalAction, internalMutation, internalQuery } from './_generated/server'
import { prepareMessageContent, prepareStoredMessageContent } from './messageContent'
import { requireOwnerDoc } from './auth/guards'
import { Permissions } from './auth/permissions'
import { authedMutation, authedQuery } from './auth/wrappers'

const DEFAULT_TITLE_MODEL = 'llama-3.1-8b-instant'
const GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions'

type GroqChatCompletionResponse = {
  choices?: Array<{
    message?: {
      content?: string | null
    }
  }>
}

const messageRoleValidator = v.union(v.literal('user'), v.literal('assistant'))

const contentFormatValidator = v.optional(
  v.union(v.literal('widget'), v.literal('text')),
)

const messageDocValidator = v.object({
  _id: v.id('messages'),
  _creationTime: v.number(),
  conversationId: v.id('conversations'),
  role: messageRoleValidator,
  content: v.string(),
  contentFormat: contentFormatValidator,
  replyToMessageId: v.optional(v.id('messages')),
  createdAt: v.number(),
})

const conversationSummaryValidator = v.object({
  _id: v.id('conversations'),
  _creationTime: v.number(),
  userId: v.id('users'),
  title: v.optional(v.string()),
  createdAt: v.number(),
  updatedAt: v.number(),
})

function resolveTitleModel(): string {
  return process.env.GROQ_TITLE_MODEL?.trim() || DEFAULT_TITLE_MODEL
}

function sanitizeGeneratedTitle(raw: string): string {
  let title = raw.trim().replace(/^["'`]+|["'`]+$/g, '')
  title = title.replace(/[.!?,;:]+$/g, '').trim()
  if (title.length > 60) {
    title = title.slice(0, 60).trim()
  }
  return title
}

function titleGenerationPrompt(userMessage: string): string {
  return `Generate a short 3-6 word title for this chat. Reply with ONLY the title, no quotes, no punctuation at end.\n\nUser message: ${userMessage}`
}

export const list = authedQuery(Permissions.readProfile, {
  args: {},
  returns: v.array(conversationSummaryValidator),
  handler: async (ctx) => {
    const rows = await ctx.db
      .query('conversations')
      .withIndex('by_user', (q) => q.eq('userId', ctx.appAuth.userId))
      .collect()

    return rows.sort((a, b) => b.updatedAt - a.updatedAt)
  },
})

export const get = authedQuery(Permissions.readProfile, {
  args: {
    conversationId: v.id('conversations'),
  },
  returns: v.object({
    conversation: conversationSummaryValidator,
    messages: v.array(messageDocValidator),
  }),
  handler: async (ctx, args) => {
    const conversation = await requireOwnerDoc(ctx, args.conversationId)
    const messages = await ctx.db
      .query('messages')
      .withIndex('by_conversation', (q) =>
        q.eq('conversationId', args.conversationId),
      )
      .collect()

    messages.sort((a, b) => a.createdAt - b.createdAt)
    return { conversation, messages }
  },
})

export const create = authedMutation(Permissions.writeProfile, {
  args: {
    title: v.optional(v.string()),
  },
  returns: v.id('conversations'),
  handler: async (ctx, args) => {
    const now = Date.now()
    return await ctx.db.insert('conversations', {
      userId: ctx.appAuth.userId,
      title: args.title,
      createdAt: now,
      updatedAt: now,
    })
  },
})

export const addMessage = authedMutation(Permissions.writeProfile, {
  args: {
    conversationId: v.id('conversations'),
    role: messageRoleValidator,
    content: v.string(),
  },
  returns: v.id('messages'),
  handler: async (ctx, args) => {
    const trimmed = args.content.trim()
    if (!trimmed) {
      throw new ConvexError({
        code: 'INVALID_INPUT',
        message: 'Message cannot be empty.',
      })
    }

    const conversation = await requireOwnerDoc(ctx, args.conversationId)
    const now = Date.now()

    const messageId = await ctx.db.insert('messages', {
      conversationId: args.conversationId,
      role: args.role,
      content: prepareMessageContent(trimmed),
      createdAt: now,
    })

    const needsTitleGeneration = !conversation.title && args.role === 'user'

    await ctx.db.patch(args.conversationId, { updatedAt: now })

    if (needsTitleGeneration) {
      await ctx.scheduler.runAfter(0, internal.conversations.generateConversationTitle, {
        userId: ctx.appAuth.userId,
        conversationId: args.conversationId,
        userMessage: trimmed,
      })
    }

    return messageId
  },
})

export const updateTitle = authedMutation(Permissions.writeProfile, {
  args: {
    conversationId: v.id('conversations'),
    title: v.string(),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    await requireOwnerDoc(ctx, args.conversationId)
    const trimmed = args.title.trim()
    if (!trimmed) {
      throw new ConvexError({
        code: 'INVALID_INPUT',
        message: 'Title cannot be empty.',
      })
    }

    await ctx.db.patch(args.conversationId, {
      title: trimmed,
      updatedAt: Date.now(),
    })
    return null
  },
})

export const remove = authedMutation(Permissions.writeProfile, {
  args: {
    conversationId: v.id('conversations'),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    await requireOwnerDoc(ctx, args.conversationId)

    const messages = await ctx.db
      .query('messages')
      .withIndex('by_conversation', (q) =>
        q.eq('conversationId', args.conversationId),
      )
      .collect()

    for (const message of messages) {
      await ctx.db.delete(message._id)
    }

    await ctx.db.delete(args.conversationId)
    return null
  },
})

/** Resolves a message for reply quoting — verifies conversation ownership. */
export const getMessageForReply = internalQuery({
  args: {
    userId: v.id('users'),
    conversationId: v.id('conversations'),
    messageId: v.id('messages'),
  },
  returns: v.union(
    v.object({
      role: messageRoleValidator,
      content: v.string(),
      contentFormat: contentFormatValidator,
      threadPosition: v.number(),
      threadLength: v.number(),
    }),
    v.null(),
  ),
  handler: async (ctx, args) => {
    const conversation = await ctx.db.get(args.conversationId)
    if (!conversation || conversation.userId !== args.userId) {
      return null
    }

    const message = await ctx.db.get(args.messageId)
    if (!message || message.conversationId !== args.conversationId) {
      return null
    }

    const threadMessages = await ctx.db
      .query('messages')
      .withIndex('by_conversation', (q) =>
        q.eq('conversationId', args.conversationId),
      )
      .collect()
    threadMessages.sort((a, b) => a.createdAt - b.createdAt)

    const index = threadMessages.findIndex((row) => row._id === args.messageId)
    if (index < 0) {
      return null
    }

    return {
      role: message.role,
      content: message.content,
      contentFormat: message.contentFormat,
      threadPosition: index + 1,
      threadLength: threadMessages.length,
    }
  },
})

/** Called from chat action after Groq reply — persists user + assistant widget(s) atomically. */
export const persistExchange = internalMutation({
  args: {
    userId: v.id('users'),
    conversationId: v.id('conversations'),
    userContent: v.string(),
    replyToMessageId: v.optional(v.id('messages')),
    assistantMessages: v.array(
      v.object({
        content: v.string(),
        contentFormat: contentFormatValidator,
      }),
    ),
  },
  returns: v.object({
    needsTitleGeneration: v.boolean(),
  }),
  handler: async (ctx, args) => {
    const conversation = await ctx.db.get(args.conversationId)
    if (!conversation || conversation.userId !== args.userId) {
      throw new ConvexError({ code: 'FORBIDDEN', message: 'Access denied' })
    }

    const userTrimmed = args.userContent.trim()
    if (!userTrimmed) {
      throw new ConvexError({
        code: 'INVALID_INPUT',
        message: 'Messages cannot be empty.',
      })
    }

    const assistantRows = args.assistantMessages
      .map((message) => ({
        content: message.content.trim(),
        contentFormat: message.contentFormat,
      }))
      .filter((message) => message.content.length > 0)

    if (assistantRows.length === 0) {
      throw new ConvexError({
        code: 'INVALID_INPUT',
        message: 'Assistant reply cannot be empty.',
      })
    }

    if (args.replyToMessageId) {
      const replyTarget = await ctx.db.get(args.replyToMessageId)
      if (
        !replyTarget ||
        replyTarget.conversationId !== args.conversationId
      ) {
        throw new ConvexError({
          code: 'INVALID_INPUT',
          message: 'Referenced message not found.',
        })
      }
    }

    const now = Date.now()

    await ctx.db.insert('messages', {
      conversationId: args.conversationId,
      role: 'user',
      content: prepareMessageContent(userTrimmed),
      replyToMessageId: args.replyToMessageId,
      createdAt: now,
    })

    for (let index = 0; index < assistantRows.length; index++) {
      const row = assistantRows[index]!
      await ctx.db.insert('messages', {
        conversationId: args.conversationId,
        role: 'assistant',
        content: prepareStoredMessageContent(row.content, row.contentFormat),
        contentFormat: row.contentFormat,
        createdAt: now + 1 + index,
      })
    }

    const needsTitleGeneration = !conversation.title
    const lastCreatedAt = now + assistantRows.length

    await ctx.db.patch(args.conversationId, { updatedAt: lastCreatedAt })

    if (needsTitleGeneration) {
      await ctx.scheduler.runAfter(0, internal.conversations.generateConversationTitle, {
        userId: args.userId,
        conversationId: args.conversationId,
        userMessage: userTrimmed,
      })
    }

    return { needsTitleGeneration }
  },
})

/** Applies Groq-generated title after the first exchange (best-effort). */
export const applyGeneratedTitle = internalMutation({
  args: {
    userId: v.id('users'),
    conversationId: v.id('conversations'),
    title: v.string(),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    const conversation = await ctx.db.get(args.conversationId)
    if (!conversation || conversation.userId !== args.userId) {
      return null
    }

    if (conversation.title?.trim()) {
      return null
    }

    const trimmed = args.title.trim()
    if (!trimmed) {
      return null
    }

    await ctx.db.patch(args.conversationId, {
      title: trimmed,
      updatedAt: Date.now(),
    })
    return null
  },
})

export const generateConversationTitle = internalAction({
  args: {
    userId: v.id('users'),
    conversationId: v.id('conversations'),
    userMessage: v.string(),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    const apiKey = process.env.GROQ_API_KEY?.trim()
    if (!apiKey) {
      console.error('generateConversationTitle: GROQ_API_KEY is not configured')
      return null
    }

    const userMessage = args.userMessage.trim()
    if (!userMessage) {
      console.error('generateConversationTitle: empty user message', {
        conversationId: args.conversationId,
      })
      return null
    }

    const model = resolveTitleModel()

    try {
      const response = await fetch(GROQ_CHAT_URL, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: titleGenerationPrompt(userMessage) }],
          stream: false,
          max_tokens: 20,
        }),
      })

      const payload = (await response.json()) as GroqChatCompletionResponse
      if (!response.ok) {
        console.error('generateConversationTitle: Groq request failed', {
          conversationId: args.conversationId,
          status: response.status,
          model,
        })
        return null
      }

      const raw = payload.choices?.[0]?.message?.content?.trim()
      if (!raw) {
        console.error('generateConversationTitle: empty Groq response', {
          conversationId: args.conversationId,
          model,
        })
        return null
      }

      const title = sanitizeGeneratedTitle(raw)
      if (!title) {
        console.error('generateConversationTitle: sanitized title empty', {
          conversationId: args.conversationId,
          raw,
        })
        return null
      }

      await ctx.runMutation(internal.conversations.applyGeneratedTitle, {
        userId: args.userId,
        conversationId: args.conversationId,
        title,
      })
    } catch (error) {
      console.error('generateConversationTitle: unexpected error', {
        conversationId: args.conversationId,
        error,
      })
    }

    return null
  },
})
