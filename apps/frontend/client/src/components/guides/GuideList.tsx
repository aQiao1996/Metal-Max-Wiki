import Link from 'next/link'

import { ArrowRight } from 'lucide-react'

import type { GameVersionSlug } from '@/config/game-versions'
import {
  guideKindLabels,
  type GuidePhase,
  type GuideSummary,
} from '@/data/guides'
import { buildVersionPath } from '@/lib/version-routes'
import { Badge } from '@/components/ui/badge'

interface GuideListProps {
  guides: readonly GuideSummary[]
  phases: readonly GuidePhase[]
  version: GameVersionSlug
}

/** 按推进阶段组织章节，保留主线、准备和可选路线的区别。 */
export function GuideList({ guides, phases, version }: GuideListProps) {
  return (
    <div className="space-y-10">
      {phases.map((phase) => {
        const chapters = guides.filter((guide) => guide.phaseId === phase.id)
        if (chapters.length === 0) return null
        return (
          <section key={phase.id} id={phase.id} className="scroll-mt-24">
            <div className="mb-4 flex flex-wrap items-baseline gap-3">
              <p className="text-xs font-medium text-[var(--mm-signal)]">
                阶段 {phase.order}
              </p>
              <h2 className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]">
                {phase.titleZh}
              </h2>
              <p className="text-muted-foreground text-xs">
                {chapters.length} 章
              </p>
            </div>
            <ol className="border-border border-t">
              {chapters.map((guide) => (
                <li key={guide.slug} className="border-border border-b">
                  <Link
                    href={buildVersionPath(version, `/guides/${guide.slug}`)}
                    className="group focus-visible:ring-ring grid gap-3 py-6 transition-colors hover:bg-white/55 focus-visible:ring-2 focus-visible:outline-none sm:grid-cols-[2rem_1fr_auto] sm:gap-5 sm:px-3"
                  >
                    <span className="font-mono text-sm text-[var(--mm-signal)]">
                      {String(guide.order).padStart(2, '0')}
                    </span>
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-lg font-semibold text-[var(--mm-navy)]">
                          {guide.title.replace(/^\d{2}\s+/, '')}
                        </span>
                        <Badge
                          variant={
                            guide.kind === 'main' ? 'outline' : 'secondary'
                          }
                          className="rounded font-normal"
                        >
                          {guideKindLabels[guide.kind]}
                        </Badge>
                      </span>
                      <span className="text-muted-foreground mt-2 block max-w-3xl text-sm leading-6">
                        {guide.summary}
                      </span>
                      <span className="text-muted-foreground mt-3 block text-xs leading-6">
                        {guide.location} · {guide.stepCount} 个操作步骤
                      </span>
                    </span>
                    <ArrowRight
                      aria-hidden="true"
                      className="mt-1 hidden size-4 sm:block"
                    />
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        )
      })}
    </div>
  )
}
