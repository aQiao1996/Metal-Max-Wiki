import Link from 'next/link'

import { ArrowRight } from 'lucide-react'

import type { GameVersionSlug } from '@/config/game-versions'
import { wikiCategoriesBySlug } from '@/data/fixtures/wiki'
import { buildVersionPath } from '@/lib/version-routes'
import type { WikiEntitySummary } from '@/types/wiki'

interface EntityListProps {
  entities: readonly WikiEntitySummary[]
  version: GameVersionSlug
  emptyMessage?: string
  from?: string
}

export function EntityList({
  entities,
  version,
  emptyMessage = '这个分类还没有录入条目。',
  from,
}: EntityListProps) {
  if (entities.length === 0) {
    return (
      <div className="border-border text-muted-foreground border-y py-10 text-center text-sm">
        {emptyMessage}
      </div>
    )
  }

  return (
    <ul className="border-border border-t">
      {entities.map((entity) => {
        const category = wikiCategoriesBySlug.get(entity.category)

        return (
          <li key={`${entity.category}:${entity.slug}`}>
            <Link
              href={
                buildVersionPath(
                  version,
                  `/wiki/${entity.category}/${entity.slug}`,
                ) + (from ? `?${new URLSearchParams({ from })}` : '')
              }
              className="group border-border focus-visible:ring-ring grid gap-2 border-b py-4 transition-colors hover:bg-white/55 focus-visible:ring-2 focus-visible:outline-none sm:grid-cols-[9rem_1fr_auto] sm:items-center sm:gap-5 sm:px-3"
            >
              <span className="text-xs font-medium text-[var(--mm-signal)]">
                {category?.label ?? '百科'}
              </span>
              <span className="min-w-0">
                <span className="text-foreground block font-medium">
                  {entity.name}
                </span>
                <span className="text-muted-foreground mt-1 line-clamp-2 block text-sm leading-5">
                  {entity.summary}
                </span>
              </span>
              <ArrowRight className="text-muted-foreground group-hover:text-foreground hidden size-4 transition-transform group-hover:translate-x-1 sm:block" />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
