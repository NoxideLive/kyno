import type { Id } from '../_generated/dataModel'
import type { AuthContext } from './types'
import { isAdmin } from './permissions'

export type OwnableResource = {
  userId: Id<'users'>
}

export function canAccessResource(appAuth: AuthContext, resource: OwnableResource): boolean {
  if (isAdmin(appAuth.role)) return true
  return resource.userId === appAuth.userId
}

export function filterAccessibleResources<T extends OwnableResource>(
  appAuth: AuthContext,
  rows: T[],
): T[] {
  if (isAdmin(appAuth.role)) return rows
  return rows.filter((row) => canAccessResource(appAuth, row))
}

export function assertCanAccessResource(
  appAuth: AuthContext,
  resource: OwnableResource,
): void {
  if (!canAccessResource(appAuth, resource)) {
    throw new Error('Access denied')
  }
}
