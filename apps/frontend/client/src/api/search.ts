import { z } from 'zod'

import { equipmentPageSchema } from '@/api/equipment'
import { request } from '@/lib/request'

const searchResultSchema = z
  .object({
    id: z.string().min(1),
    kind: z.enum(['entity', 'guide']),
    name: z.string().min(1),
    summary: z.string(),
    aliases: z.array(z.string()),
    href: z.string().regex(/^\/(?:wiki|guides)\/[a-z0-9/-]+$/),
    categoryLabel: z.string(),
    verificationStatus: z.enum(['source_only', 'compatible_candidate']),
    nameSource: z.enum(['zh_099', 'zh_09', 'zh_reference', 'ja']),
  })
  .strict()

export const librarySearchPageSchema = z
  .object({
    list: z.array(searchResultSchema),
    pagination: equipmentPageSchema.shape.pagination,
  })
  .strict()

export const suggestedSearches = ['宇宙炮', 'DDT暴雨', '亚当蚁'] as const

/** 搜索当前版本资料，并取消已经过期的查询。 */
export function searchLibrary(
  version: string,
  q: string,
  signal?: AbortSignal,
) {
  return request(
    `/api/v1/versions/${encodeURIComponent(version)}/search?${new URLSearchParams({ q, pageSize: '10' })}`,
    librarySearchPageSchema,
    { signal },
  )
}
