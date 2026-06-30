import { computed } from 'vue'
import { useAuth } from '@clerk/vue'
import { useOptionalConvexQuery } from '@/composables/useOptionalConvexQuery'
import { api } from '../../convex/_generated/api'
import { hasPermission, isAdmin, type AppRole, type Permission } from '@/lib/permissions'

export function usePermissions() {
  const { isSignedIn, isLoaded } = useAuth()

  const { data: role } = useOptionalConvexQuery(
    api.users.getMyRole,
    () => (isLoaded.value && isSignedIn.value ? {} : 'skip'),
  )

  const appRole = computed<AppRole | null>(() => role.value ?? null)

  function can(permission: Permission): boolean {
    const r = appRole.value
    if (!r) return false
    return hasPermission(r, permission)
  }

  const isAppAdmin = computed(() => (appRole.value ? isAdmin(appRole.value) : false))

  return {
    role: appRole,
    can,
    isAppAdmin,
    canReadUsers: computed(() => can('read:users')),
    canWriteUsers: computed(() => can('write:users')),
    canReadProfile: computed(() => can('read:profile')),
    canWriteProfile: computed(() => can('write:profile')),
  }
}

export function usePermissionGate(permission: Permission) {
  const { can, role } = usePermissions()
  return computed(() => {
    const r = role.value
    if (!r) return false
    return can(permission)
  })
}

export type { AppRole, Permission }
