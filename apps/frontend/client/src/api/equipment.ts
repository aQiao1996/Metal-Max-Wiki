import { z } from 'zod'

import { rawEquipmentRecordSchema } from '@/data/equipment/schema'
import { toEquipmentEntry } from '@/data/equipment/entry'
import { request } from '@/lib/request'
import { equipmentTypeIds, type EquipmentEntry } from '@/types/equipment'
import type { SearchResult } from '@/types/wiki'

function restoreSourceKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(restoreSourceKeys)
  if (typeof value !== 'object' || value === null) return value
  const entries: [string, unknown][] = Object.entries(value)
  return Object.fromEntries(
    entries.map(([key, item]) => [
      key === 'zh09'
        ? 'zh_09'
        : key === 'zh099'
          ? 'zh_099'
          : key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
      restoreSourceKeys(item),
    ]),
  )
}

const apiRecordSchema = z
  .preprocess(restoreSourceKeys, rawEquipmentRecordSchema)
  .transform(toEquipmentEntry)
export const equipmentPageSchema = z.object({
  list: z.array(apiRecordSchema),
  typeCounts: z.record(
    z.enum(equipmentTypeIds),
    z.number().int().nonnegative(),
  ),
  elements: z.array(z.string()),
  pagination: z.object({
    page: z.number().int().positive(),
    pageSize: z.number().int().positive(),
    total: z.number().int().nonnegative(),
    totalPages: z.number().int().nonnegative(),
    hasNext: z.boolean(),
    hasPrev: z.boolean(),
  }),
})

export const suggestedSearches = ['宇宙炮', '爆裂弩', '44玛格南枪'] as const

/** 将真实装备转换为搜索结果，所有链接指向稳定 ID。 */
export function toSearchResult(entry: EquipmentEntry): SearchResult {
  return {
    id: entry.id,
    kind: 'entity',
    name: entry.name,
    aliases: entry.names.aliases,
    summary: ['attack_raw', 'range_raw', 'acquisition_raw']
      .map((key) => entry.attributes[key])
      .filter((value) => value !== undefined)
      .join(' · '),
    href: `/wiki/equipment/${entry.id}`,
    categoryLabel: entry.type === 'main-cannon' ? '主炮' : '人类武器',
  }
}

/** 从同源接口搜索装备，支持取消已经过期的查询。 */
export function searchEquipment(
  version: string,
  q: string,
  signal?: AbortSignal,
) {
  return request(
    `/api/v1/versions/${encodeURIComponent(version)}/search?${new URLSearchParams({ q, pageSize: '10' })}`,
    equipmentPageSchema,
    { signal },
  )
}
