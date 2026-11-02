import Link from 'next/link'

import { ArrowRight } from 'lucide-react'

import type { GameVersionSlug } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import { formatReaderText } from '@/lib/reader-text'
import type { SearchResult } from '@/types/wiki'

interface SearchResultListProps {
  results: readonly SearchResult[]
  version: GameVersionSlug
}

export function SearchResultList({ results, version }: SearchResultListProps) {
  return (
    <ul className="border-border border-t">
      {results.map((result) => (
        <li key={result.id} className="border-border border-b">
          <Link
            href={buildVersionPath(version, result.href)}
            className="group focus-visible:ring-ring grid gap-2 py-5 transition-colors hover:bg-white/55 focus-visible:ring-2 focus-visible:outline-none sm:grid-cols-[8rem_1fr_auto] sm:items-start sm:gap-6 sm:px-3"
          >
            <span className="pt-0.5 text-xs font-medium text-[var(--mm-signal)]">
              {result.categoryLabel}
            </span>
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2 text-lg font-semibold text-[var(--mm-navy)]">
                <span>{result.name}</span>
              </span>
              {result.nameSource === 'zh_reference' && (
                <span className="text-muted-foreground mt-1 block text-xs">
                  中文参考译名
                </span>
              )}
              {result.aliases.length > 0 && (
                <span className="text-muted-foreground mt-1 block text-xs">
                  别名：{result.aliases.join(' / ')}
                </span>
              )}
              <span className="text-muted-foreground mt-2 block text-sm leading-6">
                {formatReaderText(result.summary)}
              </span>
            </span>
            <ArrowRight className="text-muted-foreground group-hover:text-foreground mt-1 hidden size-4 transition-transform group-hover:translate-x-1 sm:block" />
          </Link>
        </li>
      ))}
    </ul>
  )
}
