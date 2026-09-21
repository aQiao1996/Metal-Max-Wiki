import Link from 'next/link'
import { notFound } from 'next/navigation'

import { ArrowRight, Bot, CircleDot } from 'lucide-react'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import {
  featuredEntity,
  recentEntities,
  recentGuides,
} from '@/data/fixtures/home'
import { wikiCategories } from '@/data/fixtures/wiki'
import { buildVersionPath } from '@/lib/version-routes'
import { CategoryGrid } from '@/components/wiki/CategoryGrid'
import { EntityList } from '@/components/wiki/EntityList'

interface VersionHomePageProps {
  params: Promise<{ version: string }>
}

export default async function VersionHomePage({
  params,
}: VersionHomePageProps) {
  const { version: versionSlug } = await params
  const version = getGameVersion(versionSlug)

  if (!version) {
    notFound()
  }

  if (!isAvailableGameVersion(version)) {
    return (
      <section className="mx-auto max-w-2xl py-14 sm:py-24">
        <p className="text-xs font-semibold tracking-[0.16em] text-[var(--mm-signal)] uppercase">
          Dataset planned
        </p>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          {version.game}
        </h1>
        <p className="text-muted-foreground mt-3 text-lg">
          {version.version}，资料结构已预留，内容尚未录入。
        </p>
        <Link
          href="/v/mm2r-099"
          className="focus-visible:ring-ring mt-8 inline-flex min-h-11 items-center gap-2 rounded-md bg-[var(--mm-navy)] px-4 text-sm font-medium text-white hover:bg-[var(--mm-navy-deep)] focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          查看 2R / 0.99 资料
          <ArrowRight className="size-4" />
        </Link>
      </section>
    )
  }

  return (
    <div className="space-y-14 pb-10 lg:space-y-16">
      <section aria-labelledby="overview-heading">
        <div className="border-border flex flex-col justify-between gap-6 border-b pb-7 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2 text-xs font-medium text-[var(--mm-signal)]">
              <CircleDot className="size-3.5" />
              <span>{version.version}</span>
            </div>
            <h1
              id="overview-heading"
              className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-[var(--mm-navy)] sm:text-4xl lg:text-[2.75rem]"
            >
              情报总览
            </h1>
            <p className="text-muted-foreground mt-3 max-w-2xl text-base leading-7 text-pretty">
              按车辆、装备、赏金首和职业整理的版本化资料库。
            </p>
          </div>
          <div className="text-muted-foreground text-sm sm:text-right">
            <span className="block text-2xl font-semibold text-[var(--mm-navy)] tabular-nums">
              {wikiCategories.length}
            </span>
            <span>资料门类</span>
          </div>
        </div>

        <div className="mt-7">
          <CategoryGrid categories={wikiCategories} version={version.slug} />
        </div>
      </section>

      <section className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem] xl:gap-10">
        <div>
          <div className="mb-5 flex items-end justify-between gap-4">
            <div>
              <p className="text-muted-foreground text-xs font-medium tracking-[0.14em] uppercase">
                Recently organized
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[var(--mm-navy)]">
                最近整理
              </h2>
            </div>
            <Link
              href={buildVersionPath(version.slug, '/search')}
              className="focus-visible:ring-ring text-sm font-medium text-[var(--mm-signal)] hover:underline hover:underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
            >
              查看全部
            </Link>
          </div>
          <EntityList entities={recentEntities} version={version.slug} />
        </div>

        <aside className="border-border bg-card border p-5 sm:p-6">
          <div className="bg-muted text-muted-foreground flex aspect-[4/3] items-center justify-center border border-dashed border-[#b7c3c7] text-center text-xs tracking-wide">
            [战车实机图 · 4:3]
          </div>
          <p className="mt-5 text-[11px] font-medium tracking-[0.14em] text-[var(--mm-signal)] uppercase">
            Featured entry
          </p>
          <h2 className="mt-2 text-xl font-semibold text-[var(--mm-navy)]">
            {featuredEntity.name}
          </h2>
          <p className="text-muted-foreground mt-2 text-sm leading-6">
            {featuredEntity.summary}
          </p>
          <Link
            href={buildVersionPath(
              version.slug,
              `/wiki/${featuredEntity.category}/${featuredEntity.slug}`,
            )}
            className="focus-visible:ring-ring mt-5 inline-flex items-center gap-2 text-sm font-medium text-[var(--mm-navy)] hover:text-[var(--mm-signal)] focus-visible:ring-2 focus-visible:outline-none"
          >
            查看条目
            <ArrowRight className="size-4" />
          </Link>
        </aside>
      </section>

      <section>
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-muted-foreground text-xs font-medium tracking-[0.14em] uppercase">
              Field notes
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[var(--mm-navy)]">
              攻略与记录
            </h2>
          </div>
          <Link
            href={buildVersionPath(version.slug, '/guides')}
            className="focus-visible:ring-ring text-sm font-medium text-[var(--mm-signal)] hover:underline hover:underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
          >
            全部攻略
          </Link>
        </div>
        <div className="border-border grid border-t border-l md:grid-cols-2">
          {recentGuides.map((guide) => (
            <Link
              key={guide.slug}
              href={buildVersionPath(version.slug, `/guides/${guide.slug}`)}
              className="group border-border bg-card focus-visible:ring-ring border-r border-b p-5 transition-colors hover:bg-[#f8fafb] focus-visible:z-10 focus-visible:ring-2 focus-visible:outline-none sm:p-6"
            >
              <span className="text-muted-foreground text-xs">
                {guide.sectionCount} 个部分
              </span>
              <h3 className="mt-3 text-lg font-semibold text-[var(--mm-navy)] group-hover:text-[var(--mm-signal)]">
                {guide.title}
              </h3>
              <p className="text-muted-foreground mt-2 text-sm leading-6">
                {guide.summary}
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-border grid gap-5 border-y bg-[var(--mm-navy)] px-5 py-6 text-white sm:grid-cols-[auto_1fr_auto] sm:items-center sm:px-7">
        <div className="flex size-10 items-center justify-center rounded-md bg-white/10">
          <Bot className="size-5 text-[#ff9a76]" />
        </div>
        <div>
          <h2 className="font-semibold">基于已发布资料提问</h2>
          <p className="mt-1 text-sm leading-6 text-white/62">
            AI 问答需要登录，回答将保留当前版本范围和引用位置。
          </p>
        </div>
        <Link
          href={buildVersionPath(version.slug, '/ai')}
          className="inline-flex min-h-10 items-center justify-center gap-2 rounded-md bg-white px-4 text-sm font-medium text-[var(--mm-navy)] hover:bg-[#eef3f4] focus-visible:ring-2 focus-visible:ring-[#ff9a76] focus-visible:outline-none"
        >
          打开问答
          <ArrowRight className="size-4" />
        </Link>
      </section>
    </div>
  )
}
