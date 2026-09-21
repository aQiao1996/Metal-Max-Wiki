import Link from 'next/link'

import { ArrowRight } from 'lucide-react'

import type { GameVersionSlug } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import type { GuideSummary } from '@/types/wiki'
import { Badge } from '@/components/ui/badge'

interface GuideListProps {
  guides: readonly GuideSummary[]
  version: GameVersionSlug
}

export function GuideList({ guides, version }: GuideListProps) {
  return (
    <ol className="border-border border-t">
      {guides.map((guide, index) => (
        <li key={guide.slug} className="border-border border-b">
          <Link
            href={buildVersionPath(version, `/guides/${guide.slug}`)}
            className="group focus-visible:ring-ring grid gap-3 py-6 transition-colors hover:bg-white/55 focus-visible:ring-2 focus-visible:outline-none sm:grid-cols-[3rem_1fr_auto] sm:gap-5 sm:px-3"
          >
            <span className="font-mono text-sm text-[var(--mm-signal)]">
              {String(index + 1).padStart(2, '0')}
            </span>
            <span>
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold text-[var(--mm-navy)]">
                  {guide.title}
                </span>
                {guide.status === 'draft' && (
                  <Badge variant="secondary" className="rounded font-normal">
                    整理中
                  </Badge>
                )}
              </span>
              <span className="text-muted-foreground mt-2 block max-w-3xl text-sm leading-6">
                {guide.summary}
              </span>
              <span className="text-muted-foreground mt-3 block text-xs">
                {guide.sectionCount} 个部分
              </span>
            </span>
            <ArrowRight className="mt-1 hidden size-4 transition-transform group-hover:translate-x-1 sm:block" />
          </Link>
        </li>
      ))}
    </ol>
  )
}
