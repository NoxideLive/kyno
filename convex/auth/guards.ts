import { ConvexError } from 'convex/values'
import type { UserIdentity } from 'convex/server'
import type { Doc, Id, TableNames } from '../_generated/dataModel'
import type { MutationCtx, QueryCtx } from '../_generated/server'
import type { AuthContext } from './types'
import { hasPermission, permissionsForRole, type Permission } from './permissions'

type OwnerScopedTableName = {
  [K in TableNames]: Doc<K> extends { userId: Id<'users'> } ? K : never
}[TableNames]

type DbReader = QueryCtx['db'] | MutationCtx['db']
type AuthScopedCtx = { appAuth: AuthContext; db: DbReader }

type AuthCtx = {
  auth: { getUserIdentity: () => Promise<UserIdentity | null> }
  db: DbReader
}

export async function requireIdentity(ctx: AuthCtx) {
  const identity = await ctx.auth.getUserIdentity()
  if (!identity) {
    throw new ConvexError({ code: 'UNAUTHENTICATED', message: 'Sign in required' })
  }
  return identity
}

export async function parseAuthContext(ctx: AuthCtx): Promise<AuthContext> {
  const identity = await requireIdentity(ctx)
  const user = await ctx.db
    .query('users')
    .withIndex('by_clerk_id', (q) => q.eq('clerkId', identity.subject))
    .first()

  if (!user) {
    throw new ConvexError({
      code: 'USER_NOT_PROVISIONED',
      message: 'Account not provisioned. Sign in again.',
    })
  }

  return {
    userId: user._id,
    clerkId: identity.subject,
    role: user.role,
    email: user.email,
    name: user.name,
    permissions: permissionsForRole(user.role),
  }
}

export async function requireAuth(ctx: AuthCtx): Promise<AuthContext> {
  return parseAuthContext(ctx)
}

export function requirePermission(
  ctx: { appAuth: AuthContext },
  permission: Permission,
): void {
  if (!hasPermission(ctx.appAuth.role, permission)) {
    throw new ConvexError({
      code: 'FORBIDDEN',
      message: 'You do not have permission for this action.',
    })
  }
}

export async function requireSelfOrAdmin(
  ctx: AuthCtx,
  clerkId: string,
): Promise<AuthContext> {
  const appAuth = await parseAuthContext(ctx)
  if (appAuth.clerkId === clerkId) return appAuth
  requirePermission({ appAuth }, 'read:users')
  return appAuth
}

export async function assertOwnerDoc<TableName extends OwnerScopedTableName>(
  ctx: AuthScopedCtx,
  doc: Doc<TableName> | null,
): Promise<Doc<TableName>> {
  if (!doc) {
    throw new ConvexError({ code: 'NOT_FOUND', message: 'Resource not found' })
  }
  if (ctx.appAuth.role === 'admin') return doc
  if (doc.userId !== ctx.appAuth.userId) {
    throw new ConvexError({ code: 'FORBIDDEN', message: 'Access denied' })
  }
  return doc
}

export async function requireOwnerDoc<TableName extends OwnerScopedTableName>(
  ctx: AuthScopedCtx,
  id: Id<TableName>,
): Promise<Doc<TableName>> {
  const doc = (await ctx.db.get(id)) as Doc<TableName> | null
  return assertOwnerDoc(ctx, doc)
}

export function isSuperAdmin(clerkId: string): boolean {
  const superAdminId = process.env.SUPER_ADMIN_CLERK_ID?.trim()
  return Boolean(superAdminId && superAdminId === clerkId)
}
