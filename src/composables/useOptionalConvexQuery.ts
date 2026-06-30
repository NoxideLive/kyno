import { computed, onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'
import { useConvexClient } from 'convex-vue'
import type { FunctionArgs, FunctionReference, FunctionReturnType } from 'convex/server'

type Skip = 'skip'

/**
 * Like useConvexQuery, but accepts `'skip'` when args are not yet available.
 */
export function useOptionalConvexQuery<Query extends FunctionReference<'query'>>(
  query: Query,
  args: MaybeRefOrGetter<FunctionArgs<Query> | Skip>,
): {
  data: Ref<FunctionReturnType<Query> | undefined>
  error: Ref<Error | null>
  isPending: Ref<boolean>
} {
  const convex = useConvexClient()
  const data = ref<FunctionReturnType<Query> | undefined>()
  const error = ref<Error | null>(null)

  const resolvedArgs = computed(() => toValue(args))
  const enabled = computed(() => resolvedArgs.value !== 'skip')

  const isPending = computed(
    () => enabled.value && data.value === undefined && error.value === null,
  )

  let cancelSubscription: (() => void) | undefined

  watch(
    () =>
      resolvedArgs.value === 'skip' ? 'skip' : JSON.stringify(resolvedArgs.value),
    () => {
      const nextArgs = resolvedArgs.value
      cancelSubscription?.()
      cancelSubscription = undefined

      if (nextArgs === 'skip') {
        data.value = undefined
        error.value = null
        return
      }

      data.value = undefined
      error.value = null

      cancelSubscription = convex.onUpdate(
        query,
        nextArgs,
        (result) => {
          data.value = result
          error.value = null
        },
        (err) => {
          data.value = undefined
          error.value = err
        },
      )
    },
    { immediate: true },
  )

  onScopeDispose(() => cancelSubscription?.())

  return { data, error, isPending }
}
