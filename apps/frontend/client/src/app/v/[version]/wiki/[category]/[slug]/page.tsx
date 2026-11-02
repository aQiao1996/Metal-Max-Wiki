import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { wikiCategoriesBySlug, wikiEntities } from '@/data/fixtures/wiki'
import { getKnowledgeEntry } from '@/data/knowledge/catalog'
import { knowledgeCategorySchema } from '@/data/knowledge/schema'
import { getKnowledgeReturnHref } from '@/lib/knowledge-query'
import type { WikiCategorySlug } from '@/types/wiki'
import { AttributeTable } from '@/components/wiki/AttributeTable'
import { EntityHeader } from '@/components/wiki/EntityHeader'
import { RelatedEntries } from '@/components/wiki/RelatedEntries'
import { SourceReferences } from '@/components/wiki/SourceReferences'
import { KnowledgeDetail } from '@/components/wiki/KnowledgeDetail'

interface EntityPageProps {
  params: Promise<{ version: string; category: string; slug: string }>
  searchParams?: Promise<{ from?: string | string[] }>
}

/** 用条目名称与真实摘要生成页面元信息。 */
export async function generateMetadata({
  params,
}: EntityPageProps): Promise<Metadata> {
  const { version: versionSlug, category: categorySlug, slug } = await params
  const version = getGameVersion(versionSlug)
  if (!version || !isAvailableGameVersion(version))
    return { title: '资料未开放' }
  const parsed = knowledgeCategorySchema.safeParse(categorySlug)
  const entry = parsed.success
    ? getKnowledgeEntry(parsed.data, slug)
    : wikiEntities.find(
        (item) => item.category === categorySlug && item.slug === slug,
      )
  return entry
    ? { title: entry.name, description: entry.summary.slice(0, 160) }
    : { title: '百科条目' }
}

export default async function EntityPage({
  params,
  searchParams,
}: EntityPageProps) {
  const { version: versionSlug, category: categorySlug, slug } = await params
  const version = getGameVersion(versionSlug)
  const category = wikiCategoriesBySlug.get(categorySlug as WikiCategorySlug)

  if (!version || !isAvailableGameVersion(version) || !category) {
    notFound()
  }

  const knowledgeCategory = knowledgeCategorySchema.safeParse(categorySlug)
  if (knowledgeCategory.success) {
    const entry = getKnowledgeEntry(knowledgeCategory.data, slug)
    if (!entry) notFound()
    const query = await searchParams
    return (
      <KnowledgeDetail
        entry={entry}
        category={category}
        version={version}
        returnHref={getKnowledgeReturnHref(
          version.slug,
          knowledgeCategory.data,
          query?.from,
        )}
      />
    )
  }

  const entity = wikiEntities.find(
    (item) => item.category === categorySlug && item.slug === slug,
  )

  if (!entity) {
    notFound()
  }

  const relatedEntries = entity.relatedSlugs.flatMap((relatedSlug) => {
    const related = wikiEntities.find((item) => item.slug === relatedSlug)
    return related ? [related] : []
  })

  return (
    <article className="mx-auto max-w-6xl pb-12">
      <EntityHeader category={category} entity={entity} version={version} />

      <div className="mt-9 grid gap-12 xl:grid-cols-[minmax(0,1fr)_18rem] xl:items-start">
        <div className="min-w-0 space-y-10">
          <AttributeTable attributes={entity.attributes} />

          {entity.sections.map((section) => (
            <section key={section.id} id={section.id}>
              <h2 className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]">
                {section.title}
              </h2>
              <div className="text-foreground/82 mt-4 space-y-4 text-base leading-7 text-pretty">
                {section.paragraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
            </section>
          ))}

          <SourceReferences sources={entity.sources} />
        </div>

        <aside className="space-y-8 xl:sticky xl:top-24">
          <RelatedEntries entries={relatedEntries} version={version.slug} />
          <div className="border-border text-muted-foreground border-t pt-5 text-xs leading-5">
            <p>资料范围</p>
            <p className="text-foreground mt-1 font-medium">
              {version.game} · {version.version}
            </p>
          </div>
        </aside>
      </div>
    </article>
  )
}
