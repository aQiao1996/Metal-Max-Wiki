import type { KnowledgeCategory } from '@/data/knowledge/schema'

const tags: Partial<Record<KnowledgeCategory, readonly string[]>> = {
  items: ['人类道具', '战车道具', '特殊炮弹', 'LOVE配方', 'IC位置'],
  quests: ['普通任务', '特别委托', '有错过条件', '战车相关'],
}

/** 返回分类固定的资料类型筛选。 */
export function getKnowledgeTagOptions(category: KnowledgeCategory) {
  return tags[category] ?? []
}
