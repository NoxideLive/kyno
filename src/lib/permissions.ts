export type AppRole = 'admin' | 'user'

export type Permission =
  | 'read:profile'
  | 'write:profile'
  | 'read:users'
  | 'write:users'

export const Permissions = {
  readProfile: 'read:profile',
  writeProfile: 'write:profile',
  readUsers: 'read:users',
  writeUsers: 'write:users',
} as const satisfies Record<string, Permission>

const USER_PERMISSIONS: Permission[] = [
  Permissions.readProfile,
  Permissions.writeProfile,
]

const ADMIN_PERMISSIONS: Permission[] = [
  ...USER_PERMISSIONS,
  Permissions.readUsers,
  Permissions.writeUsers,
]

export function permissionsForRole(role: AppRole): Permission[] {
  switch (role) {
    case 'admin':
      return ADMIN_PERMISSIONS
    case 'user':
      return USER_PERMISSIONS
    default: {
      const _exhaustive: never = role
      return _exhaustive
    }
  }
}

export function hasPermission(role: AppRole, permission: Permission): boolean {
  return permissionsForRole(role).includes(permission)
}

export function isAdmin(role: AppRole): boolean {
  return role === 'admin'
}
