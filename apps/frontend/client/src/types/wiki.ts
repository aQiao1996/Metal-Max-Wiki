import { legacyEquipmentCategories } from '@/config/equipment-types'

export const wikiCategorySlugs = [
  'vehicles',
  'equipment',
  ...legacyEquipmentCategories.map(({ categorySlug }) => categorySlug),
  'wanted-monsters',
  'jobs',
] as const

export type WikiCategorySlug = (typeof wikiCategorySlugs)[number]

export interface WikiCategory {
  slug: WikiCategorySlug
  label: string
  shortLabel: string
  description: string
  index: string
}

export interface SourceReference {
  title: string
  note: string
  href: string | null
  status: 'verified' | 'pending'
}

export interface WikiAttribute {
  label: string
  value: string
  note?: string
}

export interface WikiSection {
  id: string
  title: string
  paragraphs: readonly string[]
}

export interface WikiEntitySummary {
  slug: string
  category: WikiCategorySlug
  name: string
  aliases: readonly string[]
  summary: string
  tags: readonly string[]
  verification: 'checked' | 'pending'
}

export interface WikiEntityDetail extends WikiEntitySummary {
  image: string | null
  attributes: readonly WikiAttribute[]
  sections: readonly WikiSection[]
  relatedSlugs: readonly string[]
  sources: readonly SourceReference[]
}

export interface GuideSummary {
  slug: string
  title: string
  summary: string
  sectionCount: number
  status: 'published' | 'draft'
}

export interface GuideTable {
  headers: readonly string[]
  rows: readonly (readonly string[])[]
}

export interface GuideSection {
  id: string
  title: string
  paragraphs: readonly string[]
  table?: GuideTable
}

export interface GuideDetail extends GuideSummary {
  sections: readonly GuideSection[]
  sources: readonly SourceReference[]
}

export interface SearchResult {
  id: string
  kind: 'entity' | 'guide'
  name: string
  summary: string
  aliases: readonly string[]
  href: string
  categoryLabel: string
}
