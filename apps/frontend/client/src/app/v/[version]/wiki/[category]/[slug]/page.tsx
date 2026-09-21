import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { wikiCategoriesBySlug, wikiEntities } from '@/data/fixtures/wiki'
import type { WikiCategorySlug } from '@/types/wiki'
import { AttributeTable } from '@/components/wiki/AttributeTable'
import { EntityHeader } from '@/components/wiki/EntityHeader'
import { RelatedEntries } from '@/components/wiki/RelatedEntries'
import { SourceReferences } from '@/components/wiki/SourceReferences'

export const metadata: Metadata = {
  title: '百科条目',
}

interface EntityPageProps {
  params: Promise<{ version: string; category: string; slug: string }>
}

export default async function EntityPage({ params }: EntityPageProps) {
  const { version: versionSlug, category: categorySlug, slug } = await params
  const version = getGameVersion(versionSlug)
  const category = wikiCategoriesBySlug.get(categorySlug as WikiCategorySlug)
  const entity = wikiEntities.find(
    (item) => item.category === categorySlug && item.slug === slug,
  )

  if (!version || !isAvailableGameVersion(version) || !category || !entity) {
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
