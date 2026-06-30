import type { Id } from '../_generated/dataModel'
import type { AppRole, Permission } from './permissions'

export type AuthContext = {
  userId: Id<'users'>
  clerkId: string
  role: AppRole
  email?: string
  name?: string
  permissions: Permission[]
}
