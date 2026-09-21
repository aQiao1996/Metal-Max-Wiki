import Link from 'next/link'

import { ArrowRight } from 'lucide-react'

import type { GameVersionSlug } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import type { WikiEntitySummary } from '@/types/wiki'

interface RelatedEntriesProps {
  entries: readonly WikiEntitySummary[]
  version: GameVersionSlug
}

export function RelatedEntries({ entries, version }: RelatedEntriesProps) {
  if (entries.length === 0) {
    return null
  }

  return (
    <section aria-labelledby="related-heading">
      <h2
        id="related-heading"
        className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        相关条目
      </h2>
      <ul className="border-border mt-5 border-t">
        {entries.map((entry) => (
          <li key={`${entry.category}:${entry.slug}`}>
            <Link
              href={buildVersionPath(
                version,
                `/wiki/${entry.category}/${entry.slug}`,
              )}
              className="group border-border focus-visible:ring-ring flex items-center justify-between gap-4 border-b py-4 hover:text-[var(--mm-signal)] focus-visible:ring-2 focus-visible:outline-none"
            >
              <span>
                <span className="block font-medium">{entry.name}</span>
                <span className="text-muted-foreground mt-1 line-clamp-1 block text-sm">
                  {entry.summary}
                </span>
              </span>
              <ArrowRight className="size-4 shrink-0 transition-transform group-hover:translate-x-1" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
