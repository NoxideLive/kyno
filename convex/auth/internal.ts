import { internalQuery } from '../_generated/server'
import { parseAuthContext } from './guards'

/** Auth context for actions and other non-DB Convex functions. */
export const getAuthContext = internalQuery({
  args: {},
  handler: async (ctx) => {
    return await parseAuthContext(ctx)
  },
})
