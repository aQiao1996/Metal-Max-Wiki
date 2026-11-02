import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { ExternalLink, Search } from 'lucide-react'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { getGuides, guidePhaseIdSchema } from '@/data/guides'
import { buildVersionPath } from '@/lib/version-routes'
import { GuideList } from '@/components/guides/GuideList'
import {
  formatGuideReaderNote,
  GuideDiagramFigure,
} from '@/components/guides/GuideReference'

export const metadata: Metadata = {
  title: '主线图文攻略',
  description:
    '重装机兵 2R 从开场到正式通关的 6 阶段 23 章操作参考，包含前提、步骤、关键道具、战斗要求与原创流程示意。',
}

interface GuidesPageProps {
  params: Promise<{ version: string }>
  searchParams: Promise<{ q?: string | string[]; phase?: string | string[] }>
}

export default async function GuidesPage({
  params,
  searchParams,
}: GuidesPageProps) {
  const [{ version: versionSlug }, search] = await Promise.all([
    params,
    searchParams,
  ])
  const version = getGameVersion(versionSlug)
  if (!version || !isAvailableGameVersion(version)) notFound()

  const q = ((Array.isArray(search.q) ? search.q[0] : search.q) ?? '')
    .trim()
    .slice(0, 100)
  const parsedPhase = guidePhaseIdSchema.safeParse(
    Array.isArray(search.phase) ? search.phase[0] : search.phase,
  )
  const phase = parsedPhase.success ? parsedPhase.data : ''
  const data = await getGuides(version.slug, { q, phase })
  const basePath = buildVersionPath(version.slug, '/guides')

  return (
    <div className="mx-auto max-w-5xl pb-12">
      <header className="border-border border-b pb-8">
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--mm-signal)] uppercase">
          Field guides · {version.shortLabel}
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          主线图文攻略
        </h1>
        <p className="text-muted-foreground mt-3 max-w-3xl leading-7 text-pretty">
          从马多出发到正式通关，按 6 个阶段浏览 {data.chapterCount}{' '}
          章操作清单。主线必需、推进前准备与可选支线均有单独标识。
        </p>
        <p className="border-border text-muted-foreground mt-5 max-w-3xl border-l-2 pl-4 text-sm leading-7">
          {formatGuideReaderNote(data.referenceNote)}
        </p>
      </header>

      <form
        action={basePath}
        method="get"
        className="border-border grid items-end gap-4 border-b py-6 sm:grid-cols-[1fr_13rem_auto]"
      >
        <div>
          <label htmlFor="guide-search" className="text-sm font-medium">
            查找章节或操作
          </label>
          <div className="relative mt-2">
            <Search
              aria-hidden="true"
              className="text-muted-foreground pointer-events-none absolute top-3 left-3 size-4"
            />
            <input
              id="guide-search"
              name="q"
              type="search"
              defaultValue={q}
              maxLength={100}
              placeholder="搜索地点、道具、机关或密码"
              className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border pr-3 pl-9 text-sm focus-visible:ring-2 focus-visible:outline-none"
            />
          </div>
        </div>
        <div>
          <label htmlFor="guide-phase" className="text-sm font-medium">
            推进阶段
          </label>
          <select
            id="guide-phase"
            name="phase"
            defaultValue={phase}
            className="border-input bg-background focus-visible:ring-ring mt-2 h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
          >
            <option value="">全部阶段</option>
            {data.phases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.order}. {item.titleZh}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          className="focus-visible:ring-ring inline-flex h-10 items-center justify-center rounded-md bg-[var(--mm-navy)] px-5 text-sm font-medium text-white hover:opacity-90 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          查找
        </button>
      </form>

      <div className="flex flex-wrap items-center justify-between gap-3 py-5 text-xs">
        <p className="text-muted-foreground">
          显示 {data.total} / {data.chapterCount} 章
        </p>
        {q || phase ? (
          <Link
            href={basePath}
            className="focus-visible:ring-ring py-2 text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
          >
            清除筛选
          </Link>
        ) : null}
      </div>

      {data.list.length > 0 ? (
        <>
          <nav
            aria-label="当前结果的阶段目录"
            className="mb-8 flex flex-wrap gap-x-5 gap-y-2"
          >
            {data.phases
              .filter((item) =>
                data.list.some((guide) => guide.phaseId === item.id),
              )
              .map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className="focus-visible:ring-ring py-2 text-sm text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
                >
                  {item.order}. {item.titleZh}
                </a>
              ))}
          </nav>
          <GuideList
            guides={data.list}
            phases={data.phases}
            version={version.slug}
          />
        </>
      ) : (
        <p className="border-border text-muted-foreground border-b py-12 text-sm leading-7">
          没有符合条件的章节。可以换用地点或道具名称，也可以清除筛选查看全部流程。
        </p>
      )}

      <details className="border-border mt-10 border-y py-4">
        <summary className="focus-visible:ring-ring cursor-pointer py-2 text-base font-semibold text-[var(--mm-navy)] focus-visible:ring-2 focus-visible:outline-none">
          查看通关流程总览与阅读说明
        </summary>
        <p className="text-muted-foreground mt-4 text-sm leading-7">
          {formatGuideReaderNote(data.routeNote)}
        </p>
        <div className="mt-5 space-y-5">
          {data.diagrams.map((diagram) => (
            <GuideDiagramFigure key={diagram.id} diagram={diagram} />
          ))}
        </div>
      </details>

      {data.imageReferences.length > 0 ? (
        <section className="mt-8" aria-labelledby="image-reference-heading">
          <h2
            id="image-reference-heading"
            className="text-lg font-semibold text-[var(--mm-navy)]"
          >
            外部图像资料参考
          </h2>
          <p className="text-muted-foreground mt-3 text-sm leading-7">
            尚未取得版本相符且可确认再发布的外部截图或地图许可。以下只提供来源页面链接，站内流程图均为项目原创示意。
          </p>
          <ul className="mt-3 space-y-2">
            {data.imageReferences
              .filter(
                (reference) => reference.rightsStatus === 'reference_only',
              )
              .map((reference) => (
                <li key={reference.id}>
                  <a
                    href={reference.sourcePageUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-visible:ring-ring inline-flex min-h-10 items-center gap-2 text-sm text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
                  >
                    {reference.titleZh}
                    <ExternalLink
                      aria-hidden="true"
                      className="size-3.5 shrink-0"
                    />
                  </a>
                </li>
              ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
