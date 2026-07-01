import { v } from 'convex/values'
import { mutation, query } from './_generated/server'
import { assertOwnerDoc } from './auth/guards'
import { Permissions } from './auth/permissions'
import {
  adminMutation,
  adminQuery,
  authedMutation,
  authedQuery,
} from './auth/wrappers'
import { requireIdentity, isSuperAdmin } from './auth/guards'

const userDocValidator = v.object({
  _id: v.id('users'),
  _creationTime: v.number(),
  clerkId: v.string(),
  email: v.optional(v.string()),
  name: v.optional(v.string()),
  role: v.union(v.literal('admin'), v.literal('user')),
  createdAt: v.number(),
})

/** Provision Convex user on first sign-in (raw mutation — user row may not exist yet). */
export const getOrCreateUser = mutation({
  args: {},
  returns: userDocValidator,
  handler: async (ctx) => {
    const identity = await requireIdentity(ctx)

    const existing = await ctx.db
      .query('users')
      .withIndex('by_clerk_id', (q) => q.eq('clerkId', identity.subject))
      .first()

    if (existing) return existing

    const now = Date.now()
    const userId = await ctx.db.insert('users', {
      clerkId: identity.subject,
      email: identity.email,
      name: identity.name,
      role: isSuperAdmin(identity.subject) ? 'admin' : 'user',
      createdAt: now,
    })

    await ctx.db.insert('profiles', {
      userId,
      bio: undefined,
      updatedAt: now,
    })

    const user = await ctx.db.get(userId)
    if (!user) throw new Error('Failed to create user')
    return user
  },
})

/** Role lookup for route guards (handles unauthenticated / unprovisioned). */
export const getMyRole = query({
  args: {},
  returns: v.union(v.literal('admin'), v.literal('user'), v.null()),
  handler: async (ctx) => {
    const identity = await ctx.auth.getUserIdentity()
    if (!identity) return null

    const user = await ctx.db
      .query('users')
      .withIndex('by_clerk_id', (q) => q.eq('clerkId', identity.subject))
      .first()

    return user?.role ?? null
  },
})

export const getMyProfile = authedQuery(Permissions.readProfile, {
  args: {},
  handler: async (ctx) => {
    const profile = await ctx.db
      .query('profiles')
      .withIndex('by_user', (q) => q.eq('userId', ctx.appAuth.userId))
      .first()

    const user = await ctx.db.get(ctx.appAuth.userId)
    return { user, profile }
  },
})

export const updateMyProfile = authedMutation(Permissions.writeProfile, {
  args: {
    bio: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const profile = await ctx.db
      .query('profiles')
      .withIndex('by_user', (q) => q.eq('userId', ctx.appAuth.userId))
      .first()

    const now = Date.now()
    if (profile) {
      await ctx.db.patch(profile._id, { bio: args.bio, updatedAt: now })
      return profile._id
    }

    return await ctx.db.insert('profiles', {
      userId: ctx.appAuth.userId,
      bio: args.bio,
      updatedAt: now,
    })
  },
})

export const listUsers = adminQuery({
  args: {},
  handler: async (ctx) => {
    return await ctx.db.query('users').collect()
  },
})

export const setRole = adminMutation({
  args: {
    userId: v.id('users'),
    role: v.union(v.literal('admin'), v.literal('user')),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity()
    if (!identity) {
      throw new Error('Sign in required')
    }

    const canManageRoles =
      isSuperAdmin(identity.subject) || ctx.appAuth.role === 'admin'
    if (!canManageRoles) {
      throw new Error('Forbidden')
    }

    const target = await ctx.db.get(args.userId)
    if (!target) throw new Error('User not found')

    await ctx.db.patch(args.userId, { role: args.role })
    return args.userId
  },
})

export const getProfileByUserId = authedQuery(Permissions.readProfile, {
  args: {
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    if (ctx.appAuth.role !== 'admin' && args.userId !== ctx.appAuth.userId) {
      throw new Error('Forbidden')
    }

    const profile = await ctx.db
      .query('profiles')
      .withIndex('by_user', (q) => q.eq('userId', args.userId))
      .first()

    if (profile) {
      await assertOwnerDoc(ctx, profile)
    }

    return profile
  },
})
