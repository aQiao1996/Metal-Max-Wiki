import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { SearchX } from 'lucide-react'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import {
  equipmentPageSchema,
  suggestedSearches,
  toSearchResult,
} from '@/api/equipment'
import { serverRequest } from '@/lib/request/server'
import { buildVersionPath } from '@/lib/version-routes'
import { SearchField } from '@/components/search/SearchField'
import { SearchResultList } from '@/components/search/SearchResultList'

export const metadata: Metadata = {
  title: '搜索',
}

interface SearchPageProps {
  params: Promise<{ version: string }>
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>
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
  const rawPage = Array.isArray(resolvedSearchParams.page)
    ? resolvedSearchParams.page[0]
    : resolvedSearchParams.page
  const page =
    rawPage && /^[1-9][0-9]{0,3}$/.test(rawPage) ? Number(rawPage) : 1
  const pageHref = (number: number) =>
    `${buildVersionPath(version.slug, '/search')}?${new URLSearchParams({ q: query, page: String(number) })}`
  const data = query
    ? await serverRequest(
        `/versions/${version.slug}/search?${new URLSearchParams({ q: query, page: String(page), pageSize: '20' })}`,
        equipmentPageSchema,
      )
    : null
  const results = data?.list.map(toSearchResult) ?? []

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
            {suggestedSearches.map((item) => (
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
            搜索会匹配名称、别名、属性和获取地点，结果不会跨越当前版本。
          </p>
        </section>
      ) : results.length > 0 ? (
        <section className="py-8">
          <div className="mb-5 flex items-baseline justify-between gap-4">
            <h2 className="text-lg font-semibold text-[var(--mm-navy)]">
              “{query}”的搜索结果
            </h2>
            <span className="text-muted-foreground text-sm">
              共 {data?.pagination.total ?? 0} 项
            </span>
          </div>
          <SearchResultList results={results} version={version.slug} />
          {data && data.pagination.totalPages > 1 && (
            <nav
              aria-label="搜索分页"
              className="mt-6 flex items-center justify-between gap-3 text-sm"
            >
              {data.pagination.hasPrev ? (
                <Link
                  href={pageHref(page - 1)}
                  className="inline-flex min-h-11 items-center px-3 underline"
                >
                  上一页
                </Link>
              ) : (
                <span />
              )}
              <span className="text-muted-foreground">
                第 {page} / {data.pagination.totalPages} 页
              </span>
              {data.pagination.hasNext ? (
                <Link
                  href={pageHref(page + 1)}
                  className="inline-flex min-h-11 items-center px-3 underline"
                >
                  下一页
                </Link>
              ) : (
                <span />
              )}
            </nav>
          )}
        </section>
      ) : (
        <section className="flex max-w-xl flex-col items-start py-12">
          <SearchX className="size-8 text-[var(--mm-signal)]" />
          <h2 className="mt-5 text-xl font-semibold text-[var(--mm-navy)]">
            {data && data.pagination.total > 0
              ? '这一页没有结果'
              : `没有找到“${query}”`}
          </h2>
          <p className="text-muted-foreground mt-2 text-sm leading-6">
            先确认当前版本，再尝试武器简称、战车别名或更短的关键词。
          </p>
          {data && data.pagination.total > 0 && (
            <Link
              href={pageHref(1)}
              className="mt-4 inline-flex min-h-11 items-center underline"
            >
              返回第一页结果
            </Link>
          )}
        </section>
      )}
    </div>
  )
}
