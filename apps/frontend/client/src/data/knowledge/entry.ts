import type { EquipmentNameSource } from '@/types/equipment'
import type { SourceReference, WikiEntitySummary } from '@/types/wiki'

import type { RawKnowledgeRecord, RawKnowledgeSummary } from './schema'

export interface KnowledgeEntry extends RawKnowledgeRecord {
  name: string
  nameSource: EquipmentNameSource
}

/** 选用有依据的显示名称，缺失名称时拒绝展示。 */
export function toKnowledgeEntry<T extends RawKnowledgeSummary>(
  record: T,
): T & { name: string; nameSource: EquipmentNameSource } {
  for (const source of ['zh_099', 'zh_09', 'zh_reference', 'ja'] as const) {
    const name = record.names[source]
    if (name) return { ...record, name, nameSource: source }
  }
  throw new Error(`百科条目缺少名称：${record.id}`)
}

/** 将真实百科资料转换为分类与首页的摘要。 */
export function toKnowledgeSummary(
  entry: RawKnowledgeSummary & { name: string },
): WikiEntitySummary {
  return {
    slug: entry.id,
    category: entry.category,
    name: entry.name,
    aliases: entry.names.aliases,
    summary:
      entry.bounty === null
        ? entry.summary
        : `赏金 ${entry.bounty.toLocaleString('zh-CN')} G · ${entry.summary}`,
    tags: entry.tags,
    verification: 'pending',
  }
}

/** 按来源页面归组定位，逐行事实仍保留在条目数据中。 */
export function toKnowledgeSources(entry: KnowledgeEntry): SourceReference[] {
  const pages = new Map<string, KnowledgeEntry['source_refs']>()
  for (const source of entry.source_refs) {
    const refs = pages.get(source.source_url) ?? []
    refs.push(source)
    pages.set(source.source_url, refs)
  }
  return [...pages].map(([url, refs]) => ({
    title:
      refs[0].source_id === 'metalmaniax-mm2r'
        ? 'METAL MAniaX'
        : refs[0].source_id === 'kaerulabo-mm2r'
          ? 'カエル研究室 · 掉落概率表'
          : refs[0].source_id === 'dqff-mm2r'
            ? 'MM2R 攻略 wiki 組長式'
            : refs[0].source_id,
    note:
      [
        ...new Set(
          refs.map((ref) => {
            const anchor = new URL(ref.source_url).hash
            return anchor
              ? `原页小节 ${anchor}`
              : `表 ${ref.table_index + 1} / 行 ${ref.row_index + 1}`
          }),
        ),
      ].join('；') + ` · 采集于 ${refs[0].retrieved_at.slice(0, 10)}`,
    href: url,
    status: 'pending' as const,
  }))
}
