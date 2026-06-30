import { computed, ref, watch, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { CHAT_DEBUG_STORAGE_KEY } from '@/lib/chatDebug'

export type UseChatDebugModeReturn = {
  debugEnabled: Ref<boolean>
  showToggle: boolean
  toggleDebug: () => void
}

function readStoredDebug(): boolean {
  try {
    return sessionStorage.getItem(CHAT_DEBUG_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function writeStoredDebug(enabled: boolean): void {
  try {
    sessionStorage.setItem(CHAT_DEBUG_STORAGE_KEY, enabled ? '1' : '0')
  } catch {
    // sessionStorage may be unavailable
  }
}

export function useChatDebugMode(): UseChatDebugModeReturn {
  const route = useRoute()
  const showToggle = import.meta.env.DEV

  const debugEnabled = ref(false)

  if (showToggle) {
    debugEnabled.value = readStoredDebug()
  }

  const queryDebug = computed(() => route.query.debug === '1')

  watch(
    queryDebug,
    (fromQuery) => {
      if (!showToggle) return
      if (fromQuery) {
        debugEnabled.value = true
      }
    },
    { immediate: true },
  )

  watch(debugEnabled, (enabled) => {
    if (!showToggle) return
    writeStoredDebug(enabled)
  })

  function toggleDebug(): void {
    debugEnabled.value = !debugEnabled.value
  }

  return { debugEnabled, showToggle, toggleDebug }
}
