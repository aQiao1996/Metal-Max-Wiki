import Link from 'next/link'

import { ChevronRight, ImageIcon } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import type { WikiCategory, WikiEntityDetail } from '@/types/wiki'
import { Badge } from '@/components/ui/badge'

interface EntityHeaderProps {
  category: WikiCategory
  entity: WikiEntityDetail
  version: GameVersion
}

export function EntityHeader({ category, entity, version }: EntityHeaderProps) {
  return (
    <header>
      <nav
        aria-label="面包屑"
        className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-sm"
      >
        <Link
          href={buildVersionPath(version.slug)}
          className="hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center focus-visible:ring-2 focus-visible:outline-none"
        >
          情报总览
        </Link>
        <ChevronRight className="size-3.5" />
        <Link
          href={buildVersionPath(version.slug, `/wiki/${category.slug}`)}
          className="hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center focus-visible:ring-2 focus-visible:outline-none"
        >
          {category.label}
        </Link>
        <ChevronRight className="size-3.5" />
        <span className="text-foreground">{entity.name}</span>
      </nav>

      <div className="border-border mt-7 grid gap-7 border-b pb-9 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="rounded text-[var(--mm-navy)]">
              {version.shortLabel}
            </Badge>
            <Badge
              variant="secondary"
              className="text-muted-foreground rounded font-normal"
            >
              {entity.verification === 'checked' ? '已校对' : '待校对'}
            </Badge>
          </div>
          <h1 className="mt-5 text-3xl font-semibold tracking-[-0.035em] text-[var(--mm-navy)] sm:text-4xl lg:text-[2.75rem]">
            {entity.name}
          </h1>
          {entity.aliases.length > 0 && (
            <p className="text-muted-foreground mt-2 text-sm">
              别名：{entity.aliases.join(' / ')}
            </p>
          )}
          <p className="text-muted-foreground mt-5 max-w-3xl text-base leading-7 text-pretty sm:text-lg sm:leading-8">
            {entity.summary}
          </p>
          <div className="text-muted-foreground mt-6 flex flex-wrap gap-x-4 gap-y-2 text-xs">
            {entity.tags.map((tag) => (
              <span key={tag}>#{tag}</span>
            ))}
          </div>
        </div>

        <div className="bg-muted text-muted-foreground flex aspect-[4/3] items-center justify-center border border-dashed border-[#b7c3c7]">
          <div className="text-center">
            <ImageIcon className="mx-auto size-6" strokeWidth={1.5} />
            <span className="mt-2 block text-xs">条目实机图 · 4:3</span>
          </div>
        </div>
      </div>
    </header>
  )
}
