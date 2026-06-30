import { v } from 'convex/values'
import { authedQuery } from './wrappers'
import { Permissions } from './permissions'

export const whoami = authedQuery(Permissions.readProfile, {
  args: {},
  returns: v.object({
    userId: v.id('users'),
    clerkId: v.string(),
    role: v.union(v.literal('admin'), v.literal('user')),
    email: v.optional(v.string()),
    name: v.optional(v.string()),
  }),
  handler: async (ctx) => {
    const { appAuth } = ctx
    return {
      userId: appAuth.userId,
      clerkId: appAuth.clerkId,
      role: appAuth.role,
      email: appAuth.email,
      name: appAuth.name,
    }
  },
})
