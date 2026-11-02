import Link from 'next/link'

import { ArrowLeft, ArrowRight, ExternalLink } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import {
  guideKindLabels,
  guideReaderNote,
  type GuideDetail,
  type GuideFact,
} from '@/data/guides'
import { buildVersionPath } from '@/lib/version-routes'
import { Badge } from '@/components/ui/badge'

import { GuideDiagramFigure, GuideFactContent } from './GuideReference'

interface GuideArticleProps {
  guide: GuideDetail
  version: GameVersion
}

const battleLabels = {
  mandatory: '必需战斗',
  optional: '可选战斗',
  scripted_loss: '剧情必败',
} as const

const sections = [
  { id: 'prerequisites', title: '出发前提' },
  { id: 'steps', title: '操作步骤' },
  { id: 'key-items', title: '关键道具' },
  { id: 'battles', title: '战斗要求' },
  { id: 'cautions', title: '注意事项' },
  { id: 'next-steps', title: '下一步' },
  { id: 'diagrams', title: '原创流程示意' },
  { id: 'sources', title: '来源与校对' },
] as const

function FactSection({
  id,
  title,
  facts,
  ordered = false,
}: {
  id: string
  title: string
  facts: readonly GuideFact[]
  ordered?: boolean
}) {
  const List = ordered ? 'ol' : 'ul'
  return (
    <section id={id} className="scroll-mt-24" aria-labelledby={`${id}-heading`}>
      <h2
        id={`${id}-heading`}
        className="text-2xl font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        {title}
      </h2>
      {facts.length > 0 ? (
        <List className="mt-5 space-y-6">
          {facts.map((fact, index) => (
            <li key={fact.id} className="grid grid-cols-[1.7rem_1fr] gap-3">
              <span
                aria-hidden="true"
                className="pt-1 font-mono text-sm text-[var(--mm-signal)]"
              >
                {ordered ? String(index + 1).padStart(2, '0') : '—'}
              </span>
              <GuideFactContent fact={fact} />
            </li>
          ))}
        </List>
      ) : (
        <p className="text-muted-foreground mt-4 text-sm leading-7">
          来源未单列本章的关键道具，请结合出发前提与操作步骤准备。
        </p>
      )}
    </section>
  )
}

function ChapterNavigation({ guide, version }: GuideArticleProps) {
  return (
    <nav aria-label="按阶段跳转攻略章节" className="space-y-4">
      {guide.phases.map((phase) => (
        <details key={phase.id} open={phase.id === guide.phaseId}>
          <summary className="focus-visible:ring-ring cursor-pointer py-2 text-sm font-medium text-[var(--mm-navy)] focus-visible:ring-2 focus-visible:outline-none">
            阶段 {phase.order} · {phase.titleZh}
          </summary>
          <ol className="border-border mt-1 space-y-1 border-l pl-3">
            {guide.chapters
              .filter((chapter) => chapter.phaseId === phase.id)
              .map((chapter) => (
                <li key={chapter.slug}>
                  <Link
                    href={buildVersionPath(
                      version.slug,
                      `/guides/${chapter.slug}`,
                    )}
                    aria-current={
                      chapter.slug === guide.slug ? 'page' : undefined
                    }
                    className="text-muted-foreground focus-visible:ring-ring block py-2 text-xs leading-5 break-words hover:text-[var(--mm-signal)] focus-visible:ring-2 focus-visible:outline-none aria-[current=page]:font-semibold aria-[current=page]:text-[var(--mm-signal)]"
                  >
                    {chapter.title}
                  </Link>
                </li>
              ))}
          </ol>
        </details>
      ))}
    </nav>
  )
}

/** 服务端渲染本章完整操作与证据，章节跳转无需浏览器脚本。 */
export function GuideArticle({ guide, version }: GuideArticleProps) {
  const specificDiagrams = guide.diagrams.filter(
    (diagram) => diagram.id !== 'mainline-overview',
  )
  const diagrams =
    specificDiagrams.length > 0 ? specificDiagrams : guide.diagrams
  const previousChapter = guide.chapters.find(
    (chapter) => chapter.order === guide.order - 1,
  )

  return (
    <article className="mx-auto max-w-6xl pb-12">
      <Link
        href={buildVersionPath(version.slug, '/guides')}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center gap-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        全部攻略章节
      </Link>

      <header className="border-border mt-6 border-b pb-8">
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--mm-signal)]">
          {guide.phase.titleZh} · 第 {guide.order} / {guide.chapters.length} 章
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="rounded font-normal">
            {guideKindLabels[guide.kind]}
          </Badge>
          <span className="text-muted-foreground text-xs">
            中文参考 · {version.version} 未实机验证
          </span>
        </div>
        <h1 className="mt-4 max-w-4xl text-3xl font-semibold tracking-[-0.035em] text-[var(--mm-navy)] sm:text-4xl lg:text-[2.75rem]">
          {guide.title.replace(/^\d{2}\s+/, '')}
        </h1>
        <p className="text-muted-foreground mt-4 max-w-3xl text-lg leading-8 text-pretty">
          {guide.summary}
        </p>
        <p className="mt-4 text-sm font-medium">途经：{guide.location}</p>
        <p className="border-border text-muted-foreground mt-6 max-w-3xl border-l-2 pl-4 text-sm leading-7">
          {guideReaderNote(guide.referenceNote)}
        </p>
      </header>

      <details className="border-border mt-6 border-b pb-4 xl:hidden">
        <summary className="focus-visible:ring-ring cursor-pointer py-3 text-sm font-medium text-[var(--mm-navy)] focus-visible:ring-2 focus-visible:outline-none">
          按阶段跳转全部章节
        </summary>
        <div className="mt-3">
          <ChapterNavigation guide={guide} version={version} />
        </div>
      </details>

      <div className="mt-9 grid gap-12 xl:grid-cols-[minmax(0,46rem)_15rem] xl:justify-between">
        <div className="min-w-0 space-y-11">
          <nav aria-label="本章内容" className="flex flex-wrap gap-x-5 gap-y-2">
            {sections.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className="focus-visible:ring-ring py-2 text-xs text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
              >
                {section.title}
              </a>
            ))}
          </nav>
          <FactSection
            id="prerequisites"
            title="出发前提"
            facts={guide.prerequisites}
          />
          <FactSection
            id="steps"
            title="操作步骤"
            facts={guide.steps}
            ordered
          />
          <FactSection id="key-items" title="关键道具" facts={guide.keyItems} />

          <section
            id="battles"
            className="scroll-mt-24"
            aria-labelledby="battles-heading"
          >
            <h2
              id="battles-heading"
              className="text-2xl font-semibold tracking-tight text-[var(--mm-navy)]"
            >
              战斗要求
            </h2>
            <p className="text-muted-foreground mt-4 text-sm leading-7">
              {guide.battleNote}
            </p>
            <ul className="mt-5 space-y-6">
              {guide.battles.map((battle) => (
                <li key={battle.id} className="border-border border-l-2 pl-4">
                  <Badge
                    variant="secondary"
                    className="mb-3 rounded font-normal"
                  >
                    {battleLabels[battle.requirement]}
                  </Badge>
                  <GuideFactContent fact={battle} />
                </li>
              ))}
            </ul>
          </section>

          <FactSection id="cautions" title="注意事项" facts={guide.cautions} />
          <div>
            <FactSection
              id="next-steps"
              title="下一步"
              facts={guide.nextSteps}
            />
            {guide.nextChapters.length > 0 ? (
              <nav
                aria-label="推荐下一章"
                className="border-border mt-6 space-y-3 border-t pt-4"
              >
                {guide.nextChapters.map((chapter) => (
                  <Link
                    key={chapter.slug}
                    href={buildVersionPath(
                      version.slug,
                      `/guides/${chapter.slug}`,
                    )}
                    className="focus-visible:ring-ring flex min-h-11 items-center justify-between gap-3 py-2 text-sm font-medium text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
                  >
                    <span>{chapter.title}</span>
                    <ArrowRight
                      aria-hidden="true"
                      className="size-4 shrink-0"
                    />
                  </Link>
                ))}
              </nav>
            ) : null}
            {previousChapter ? (
              <Link
                href={buildVersionPath(
                  version.slug,
                  `/guides/${previousChapter.slug}`,
                )}
                className="text-muted-foreground focus-visible:ring-ring mt-4 inline-flex min-h-10 items-center gap-2 text-xs hover:underline focus-visible:ring-2 focus-visible:outline-none"
              >
                <ArrowLeft aria-hidden="true" className="size-3.5" />
                上一章：{previousChapter.title}
              </Link>
            ) : null}
          </div>

          <section
            id="diagrams"
            className="scroll-mt-24"
            aria-labelledby="diagrams-heading"
          >
            <h2
              id="diagrams-heading"
              className="text-2xl font-semibold tracking-tight text-[var(--mm-navy)]"
            >
              原创流程示意
            </h2>
            <p className="text-muted-foreground mt-3 text-sm leading-7">
              箭头表示事件条件和建议推进顺序，不代表地图坐标或地理距离。
            </p>
            <div className="mt-5 space-y-6">
              {diagrams.map((diagram) => (
                <GuideDiagramFigure key={diagram.id} diagram={diagram} />
              ))}
            </div>
          </section>

          <section
            id="sources"
            className="scroll-mt-24"
            aria-labelledby="sources-heading"
          >
            <h2
              id="sources-heading"
              className="text-2xl font-semibold tracking-tight text-[var(--mm-navy)]"
            >
              来源与校对
            </h2>
            <p className="text-muted-foreground mt-4 text-sm leading-7">
              操作条件依据 MM2R
              日文公开资料归纳；中文名称为参考译名。每条操作下方可展开短证据并跳转原文。来源核对不等于已在
              0.99 实机验证。
            </p>
            <ul className="border-border mt-5 divide-y border-y">
              {guide.sources.map((source) => (
                <li key={source.key} className="py-4 text-sm leading-7">
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-visible:ring-ring inline-flex items-start gap-2 break-words text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
                  >
                    <span>{source.title}</span>
                    <ExternalLink
                      aria-hidden="true"
                      className="mt-1.5 size-3.5 shrink-0"
                    />
                  </a>
                  <p className="text-muted-foreground mt-1 text-xs">
                    {source.attribution}
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs leading-6">
                    {source.rightsScopeZh}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <aside className="hidden xl:block">
          <div className="border-border sticky top-24 max-h-[calc(100dvh-8rem)] overflow-y-auto border-l pr-2 pl-5">
            <p className="text-muted-foreground mb-3 text-xs font-semibold tracking-[0.12em]">
              全部 6 阶段 · 23 章
            </p>
            <ChapterNavigation guide={guide} version={version} />
          </div>
        </aside>
      </div>
    </article>
  )
}
