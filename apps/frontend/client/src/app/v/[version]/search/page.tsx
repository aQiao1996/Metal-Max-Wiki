import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { SearchX } from 'lucide-react'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { recentSearches, searchResults } from '@/data/fixtures/search'
import { buildVersionPath } from '@/lib/version-routes'
import { SearchField } from '@/components/search/SearchField'
import { SearchResultList } from '@/components/search/SearchResultList'

export const metadata: Metadata = {
  title: '搜索',
}

interface SearchPageProps {
  params: Promise<{ version: string }>
  searchParams: Promise<{ q?: string | string[] }>
}

export default async function SearchPage({
  params,
  searchParams,
}: SearchPageProps) {
  const [{ version: versionSlug }, resolvedSearchParams] = await Promise.all([
    params,
    searchParams,
  ])
  const version = getGameVersion(versionSlug)

  if (!version || !isAvailableGameVersion(version)) {
    notFound()
  }

  const rawQuery = resolvedSearchParams.q
  const query = (Array.isArray(rawQuery) ? rawQuery[0] : rawQuery)?.trim() ?? ''
  const normalizedQuery = query.toLocaleLowerCase('zh-CN')
  const results = normalizedQuery
    ? searchResults.filter((result) =>
        [result.name, result.summary, ...result.aliases].some((value) =>
          value.toLocaleLowerCase('zh-CN').includes(normalizedQuery),
        ),
      )
    : []

  return (
    <div className="mx-auto max-w-5xl pb-10">
      <header className="border-border border-b pb-7">
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--mm-signal)] uppercase">
          Search archive
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          搜索资料库
        </h1>
        <p className="text-muted-foreground mt-3 text-sm">
          当前范围：{version.game} · {version.version}
        </p>
        <div className="mt-7">
          <SearchField defaultValue={query} />
        </div>
      </header>

      {!query ? (
        <section className="py-10">
          <h2 className="text-sm font-semibold text-[var(--mm-navy)]">
            可以从这些名称开始
          </h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {recentSearches.map((item) => (
              <Link
                key={item}
                href={`${buildVersionPath(version.slug, '/search')}?q=${encodeURIComponent(item)}`}
                className="border-border bg-card hover:bg-muted focus-visible:ring-ring inline-flex min-h-10 items-center rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
              >
                {item}
              </Link>
            ))}
          </div>
          <p className="text-muted-foreground mt-8 max-w-xl text-sm leading-6">
            搜索会匹配条目名、别名和摘要，结果不会跨越当前版本。
          </p>
        </section>
      ) : results.length > 0 ? (
        <section className="py-8">
          <div className="mb-5 flex items-baseline justify-between gap-4">
            <h2 className="text-lg font-semibold text-[var(--mm-navy)]">
              “{query}”的搜索结果
            </h2>
            <span className="text-muted-foreground text-sm">
              {results.length} 项
            </span>
          </div>
          <SearchResultList results={results} version={version.slug} />
        </section>
      ) : (
        <section className="flex max-w-xl flex-col items-start py-12">
          <SearchX className="size-8 text-[var(--mm-signal)]" />
          <h2 className="mt-5 text-xl font-semibold text-[var(--mm-navy)]">
            没有找到“{query}”
          </h2>
          <p className="text-muted-foreground mt-2 text-sm leading-6">
            先确认当前版本，再尝试武器简称、战车别名或更短的关键词。
          </p>
        </section>
      )}
    </div>
  )
}
