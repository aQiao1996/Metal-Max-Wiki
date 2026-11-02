import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound, redirect } from 'next/navigation'

import { ArrowLeft, ListFilter } from 'lucide-react'

import { getLegacyEquipmentType } from '@/config/equipment-types'
import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { wikiCategoriesBySlug, wikiEntities } from '@/data/fixtures/wiki'
import { knowledgeCategorySchema } from '@/data/knowledge/schema'
import { buildVersionPath } from '@/lib/version-routes'
import type { WikiCategorySlug } from '@/types/wiki'
import { EntityList } from '@/components/wiki/EntityList'
import {
  KnowledgeIndex,
  type KnowledgeQuery,
} from '@/components/wiki/KnowledgeIndex'

export const metadata: Metadata = {
  title: '资料分类',
}

interface CategoryPageProps {
  params: Promise<{ version: string; category: string }>
  searchParams?: Promise<KnowledgeQuery>
}

export default async function CategoryPage({
  params,
  searchParams,
}: CategoryPageProps) {
  const { version: versionSlug, category: categorySlug } = await params
  const version = getGameVersion(versionSlug)

  if (!version || !isAvailableGameVersion(version)) {
    notFound()
  }

  const legacyEquipmentType = getLegacyEquipmentType(categorySlug)

  if (legacyEquipmentType) {
    redirect(
      `${buildVersionPath(version.slug, '/wiki/equipment')}?type=${legacyEquipmentType}`,
    )
  }

  const category = wikiCategoriesBySlug.get(categorySlug as WikiCategorySlug)

  if (!category) {
    notFound()
  }

  const knowledgeCategory = knowledgeCategorySchema.safeParse(categorySlug)
  if (knowledgeCategory.success) {
    return (
      <KnowledgeIndex
        version={version}
        category={category}
        categorySlug={knowledgeCategory.data}
        query={(await searchParams) ?? {}}
      />
    )
  }

  const entities = wikiEntities.filter(
    (entity) => entity.category === category.slug,
  )

  return (
    <div className="mx-auto max-w-6xl pb-10">
      <Link
        href={buildVersionPath(version.slug)}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center gap-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" />
        情报总览
      </Link>

      <header className="border-border mt-5 border-b pb-7">
        <div className="flex items-start gap-4">
          <span className="pt-1 font-mono text-sm text-[var(--mm-signal)]">
            {category.index}
          </span>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
              {category.label}
            </h1>
            <p className="text-muted-foreground mt-3 max-w-2xl leading-7 text-pretty">
              {category.description}。当前仅显示 {version.version}资料。
            </p>
          </div>
        </div>
      </header>

      <section className="py-7">
        <div className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <p className="text-sm font-medium text-[var(--mm-navy)]">
              条目索引
            </p>
            <p className="text-muted-foreground mt-1 text-xs">
              已录入 {entities.length} 项展示资料
            </p>
          </div>
          <div
            className="flex flex-wrap items-center gap-2"
            aria-label="筛选预览"
          >
            <span className="text-muted-foreground mr-1 inline-flex items-center gap-1.5 text-xs">
              <ListFilter className="size-3.5" />
              筛选
            </span>
            {['全部类型', '全部来源', '全部状态'].map((label) => (
              <button
                key={label}
                type="button"
                disabled
                className="border-border bg-card text-muted-foreground min-h-9 rounded-md border px-3 text-xs disabled:cursor-not-allowed disabled:opacity-70"
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <EntityList
          entities={entities}
          version={version.slug}
          emptyMessage="这个分类的数据结构已预留，条目尚未录入。"
        />
      </section>
    </div>
  )
}
