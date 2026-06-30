import { action, mutation, query } from '../_generated/server'
import { internal } from '../_generated/api'
import type { ActionCtx, MutationCtx, QueryCtx } from '../_generated/server'
import type { GenericValidator, ObjectType, PropertyValidators } from 'convex/values'
import type { AuthContext } from './types'
import { parseAuthContext, requirePermission } from './guards'
import {
  Permissions,
  type MutationPermission,
  type QueryPermission,
} from './permissions'

export type AuthedQueryCtx = QueryCtx & { appAuth: AuthContext }
export type AuthedMutationCtx = MutationCtx & { appAuth: AuthContext }
export type AuthedActionCtx = ActionCtx & { appAuth: AuthContext }

type AuthedQueryConfig<ArgsValidator extends PropertyValidators = PropertyValidators> = {
  args?: ArgsValidator
  returns?: GenericValidator
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: (ctx: AuthedQueryCtx, args: ObjectType<ArgsValidator>) => any
}

type AuthedMutationConfig<ArgsValidator extends PropertyValidators> = {
  args: ArgsValidator
  returns?: GenericValidator
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: (ctx: AuthedMutationCtx, args: ObjectType<ArgsValidator>) => any
}

type AuthedActionConfig<ArgsValidator extends PropertyValidators> = {
  args: ArgsValidator
  returns?: GenericValidator
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handler: (ctx: AuthedActionCtx, args: ObjectType<ArgsValidator>) => any
}

export function authedQuery<ArgsValidator extends PropertyValidators = PropertyValidators>(
  permission: QueryPermission,
  config: AuthedQueryConfig<ArgsValidator>,
) {
  return query({
    args: config.args ?? {},
    returns: config.returns,
    handler: async (ctx, args) => {
      const appAuth = await parseAuthContext(ctx)
      requirePermission({ appAuth }, permission)
      const authedCtx: AuthedQueryCtx = Object.assign(ctx, { appAuth })
      return config.handler(authedCtx, args as ObjectType<ArgsValidator>)
    },
  })
}

export function authedMutation<ArgsValidator extends PropertyValidators>(
  permission: MutationPermission,
  config: AuthedMutationConfig<ArgsValidator>,
) {
  return mutation({
    args: config.args,
    returns: config.returns,
    // @ts-expect-error Convex registrar handler variance at factory boundary.
    handler: async (ctx, args) => {
      const appAuth = await parseAuthContext(ctx)
      requirePermission({ appAuth }, permission)
      const authedCtx: AuthedMutationCtx = Object.assign(ctx, { appAuth })
      return config.handler(authedCtx, args as ObjectType<ArgsValidator>)
    },
  })
}

export function adminQuery<ArgsValidator extends PropertyValidators = PropertyValidators>(
  config: AuthedQueryConfig<ArgsValidator>,
) {
  return authedQuery(Permissions.readUsers, config)
}

export function adminMutation<ArgsValidator extends PropertyValidators>(
  config: AuthedMutationConfig<ArgsValidator>,
) {
  return authedMutation(Permissions.writeUsers, config)
}

export function authedAction<ArgsValidator extends PropertyValidators>(
  permission: QueryPermission,
  config: AuthedActionConfig<ArgsValidator>,
) {
  return action({
    args: config.args,
    returns: config.returns,
    // @ts-expect-error Convex registrar handler variance at factory boundary.
    handler: async (ctx, args) => {
      const appAuth = await ctx.runQuery(internal.auth.internal.getAuthContext, {})
      requirePermission({ appAuth }, permission)
      const authedCtx: AuthedActionCtx = Object.assign(ctx, { appAuth })
      return config.handler(authedCtx, args as ObjectType<ArgsValidator>)
    },
  })
}

export { query, mutation, action }
