import type { QueryClient } from '@tanstack/react-query'
import type { LibraryItem } from '@/types'

/** Remove library item(s) from cache immediately; returns snapshot for rollback. */
export async function optimisticRemoveLibraryItems(
  queryClient: QueryClient,
  ids: number | number[]
): Promise<{ previous: LibraryItem[] | undefined }> {
  await queryClient.cancelQueries({ queryKey: ['library'] })
  const previous = queryClient.getQueryData<LibraryItem[]>(['library'])
  const idSet = new Set(Array.isArray(ids) ? ids : [ids])
  if (previous) {
    queryClient.setQueryData(
      ['library'],
      previous.filter((item) => !idSet.has(item.id))
    )
  }
  return { previous }
}

export function restoreLibraryCache(
  queryClient: QueryClient,
  previous: LibraryItem[] | undefined
): void {
  if (previous) {
    queryClient.setQueryData(['library'], previous)
  }
}
