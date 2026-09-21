import Link from 'next/link'

import { ArrowUpRight } from 'lucide-react'

import type { GameVersionSlug } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import type { WikiCategory } from '@/types/wiki'

interface CategoryGridProps {
  categories: readonly WikiCategory[]
  version: GameVersionSlug
}

export function CategoryGrid({ categories, version }: CategoryGridProps) {
  return (
    <div className="border-border grid grid-cols-2 border-t border-l lg:grid-cols-4">
      {categories.map((category) => (
        <Link
          key={category.slug}
          href={buildVersionPath(version, `/wiki/${category.slug}`)}
          className="group border-border bg-card focus-visible:ring-ring min-h-36 border-r border-b p-4 transition-colors hover:bg-[#f8fafb] focus-visible:z-10 focus-visible:ring-2 focus-visible:outline-none sm:min-h-40 sm:p-5"
        >
          <div className="flex items-start justify-between gap-4">
            <span className="font-mono text-[11px] tracking-[0.1em] text-[var(--mm-signal)]">
              {category.index}
            </span>
            <ArrowUpRight className="text-muted-foreground size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-[var(--mm-signal)]" />
          </div>
          <h3 className="mt-7 text-lg font-semibold tracking-tight text-[var(--mm-navy)] sm:mt-9">
            {category.label}
          </h3>
          <p className="text-muted-foreground mt-2 line-clamp-2 text-xs leading-5 sm:text-sm">
            {category.description}
          </p>
        </Link>
      ))}
    </div>
  )
}
