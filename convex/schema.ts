import { defineSchema, defineTable } from 'convex/server'
import { v } from 'convex/values'

export default defineSchema({
  users: defineTable({
    clerkId: v.string(),
    email: v.optional(v.string()),
    name: v.optional(v.string()),
    role: v.union(v.literal('admin'), v.literal('user')),
    createdAt: v.number(),
  })
    .index('by_clerk_id', ['clerkId']),

  profiles: defineTable({
    userId: v.id('users'),
    bio: v.optional(v.string()),
    updatedAt: v.number(),
  }).index('by_user', ['userId']),

  conversations: defineTable({
    userId: v.id('users'),
    title: v.optional(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  }).index('by_user', ['userId']),

  messages: defineTable({
    conversationId: v.id('conversations'),
    role: v.union(v.literal('user'), v.literal('assistant')),
    content: v.string(),
    contentFormat: v.optional(v.union(v.literal('widget'), v.literal('text'))),
    replyToMessageId: v.optional(v.id('messages')),
    createdAt: v.number(),
  }).index('by_conversation', ['conversationId']),
})
