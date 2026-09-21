import { guides } from '@/data/fixtures/guides'
import { wikiCategoriesBySlug, wikiEntities } from '@/data/fixtures/wiki'
import type { SearchResult } from '@/types/wiki'

export const searchResults = [
  ...wikiEntities.map((entity) => ({
    id: `entity:${entity.category}:${entity.slug}`,
    kind: 'entity' as const,
    name: entity.name,
    summary: entity.summary,
    aliases: entity.aliases,
    href: `/wiki/${entity.category}/${entity.slug}`,
    categoryLabel:
      wikiCategoriesBySlug.get(entity.category)?.label ?? '百科条目',
  })),
  ...guides.map((guide) => ({
    id: `guide:${guide.slug}`,
    kind: 'guide' as const,
    name: guide.title,
    summary: guide.summary,
    aliases: [],
    href: `/guides/${guide.slug}`,
    categoryLabel: '攻略',
  })),
] satisfies readonly SearchResult[]

export const recentSearches = ['红狼战车', '宇宙炮', 'DDT 暴雨'] as const
