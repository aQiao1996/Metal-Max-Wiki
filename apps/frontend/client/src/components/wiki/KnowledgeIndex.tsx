import Link from 'next/link'

import { ArrowLeft } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { getKnowledgeTagOptions } from '@/config/knowledge-filters'
import { knowledgePageSchema } from '@/api/knowledge'
import { toKnowledgeSummary } from '@/data/knowledge/entry'
import type { KnowledgeCategory } from '@/data/knowledge/schema'
import { serverRequest } from '@/lib/request/server'
import { buildVersionPath } from '@/lib/version-routes'
import type { WikiCategory } from '@/types/wiki'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EntityList } from '@/components/wiki/EntityList'

export interface KnowledgeQuery {
  q?: string | string[]
  sort?: string | string[]
  page?: string | string[]
  mount?: string | string[]
  tag?: string | string[]
}

interface KnowledgeIndexProps {
  version: GameVersion
  category: WikiCategory
  categorySlug: KnowledgeCategory
  query: KnowledgeQuery
}

/** 使用网址参数筛选真实百科条目，便于分享与返回。 */
export async function KnowledgeIndex({
  version,
  category,
  categorySlug,
  query,
}: KnowledgeIndexProps) {
  const first = (value: string | string[] | undefined) =>
    Array.isArray(value) ? value[0] : value
  const q = (first(query.q) ?? '').trim().slice(0, 100)
  const sort =
    categorySlug === 'wanted-monsters' && first(query.sort) === 'bounty-desc'
      ? 'bounty-desc'
      : 'name-asc'
  const rawMount = first(query.mount)
  const mount =
    categorySlug === 'vehicles' &&
    (rawMount === 'double-engine' || rawMount === 'double-c-unit')
      ? rawMount
      : 'all'
  const rawPage = first(query.page)
  const tagOptions = getKnowledgeTagOptions(categorySlug)
  const rawTag = first(query.tag) ?? ''
  const tag = tagOptions.includes(rawTag) ? rawTag : ''
  const page =
    rawPage && /^[1-9][0-9]{0,3}$/.test(rawPage) ? Number(rawPage) : 1
  const path = buildVersionPath(version.slug, `/wiki/${categorySlug}`)
  const parameters = new URLSearchParams({
    q,
    sort,
    page: String(page),
    pageSize: '20',
  })
  if (mount !== 'all') parameters.set('mount', mount)
  if (tag) parameters.set('tag', tag)
  const data = await serverRequest(
    `/versions/${version.slug}/wiki/${categorySlug}?${parameters}`,
    knowledgePageSchema,
  )
  const listParameters = (targetPage: number) => {
    const values = new URLSearchParams({ q, sort, page: String(targetPage) })
    if (mount !== 'all') values.set('mount', mount)
    if (tag) values.set('tag', tag)
    return values
  }
  const href = (targetPage: number) => `${path}?${listParameters(targetPage)}`
  return (
    <div className="mx-auto max-w-6xl min-w-0 pb-10">
      <Link
        href={buildVersionPath(version.slug)}
        className="text-muted-foreground focus-visible:ring-ring inline-flex min-h-10 items-center gap-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        情报总览
      </Link>
      <header className="border-border mt-5 border-b pb-7">
        <p className="font-mono text-xs text-[var(--mm-signal)]">
          {category.index} / {version.shortLabel}
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          {category.label}
        </h1>
        <p className="text-muted-foreground mt-3 text-sm leading-7">
          {category.description}
        </p>
      </header>
      <form
        action={path}
        method="get"
        className="border-border grid items-end gap-4 border-b py-6 sm:grid-cols-[minmax(0,1fr)_12rem_auto]"
      >
        <div>
          <label
            htmlFor="knowledge-query"
            className="mb-2 block text-sm font-medium"
          >
            搜索{category.label}
          </label>
          <Input
            id="knowledge-query"
            name="q"
            type="search"
            maxLength={100}
            defaultValue={q}
            placeholder={
              categorySlug === 'vehicles'
                ? '车型、型号或特性'
                : categorySlug === 'jobs'
                  ? '职业、技能或作用'
                  : categorySlug === 'items'
                    ? '名称、用途、配方或地点'
                    : categorySlug === 'quests'
                      ? '任务、接取地点或条件'
                      : '名称、地点或掉落物品'
            }
          />
        </div>
        <div>
          <label
            htmlFor={
              categorySlug === 'vehicles' ? 'knowledge-mount' : 'knowledge-sort'
            }
            className="mb-2 block text-sm font-medium"
          >
            {categorySlug === 'vehicles'
              ? '动力配置'
              : tagOptions.length
                ? '资料类型'
                : '排序'}
          </label>
          <select
            id={
              categorySlug === 'vehicles' ? 'knowledge-mount' : 'knowledge-sort'
            }
            name={
              categorySlug === 'vehicles'
                ? 'mount'
                : tagOptions.length
                  ? 'tag'
                  : 'sort'
            }
            defaultValue={
              categorySlug === 'vehicles'
                ? mount
                : tagOptions.length
                  ? tag
                  : sort
            }
            className="border-input bg-card focus-visible:ring-ring h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
          >
            {categorySlug === 'vehicles' ? (
              <>
                <option value="all">全部车型</option>
                <option value="double-engine">支持双引擎</option>
                <option value="double-c-unit">支持双 C</option>
              </>
            ) : tagOptions.length ? (
              <>
                <option value="">全部类型</option>
                {tagOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </>
            ) : (
              <>
                <option value="name-asc">名称升序</option>
                {categorySlug === 'wanted-monsters' && (
                  <option value="bounty-desc">赏金降序</option>
                )}
              </>
            )}
          </select>
        </div>
        <div className="flex min-h-10 items-center gap-4">
          <Button type="submit">应用条件</Button>
          <Link
            href={path}
            className="focus-visible:ring-ring inline-flex min-h-10 items-center text-sm underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
          >
            清空条件
          </Link>
        </div>
      </form>
      <p className="text-muted-foreground py-5 text-sm">
        共 {data.pagination.total} 条符合条件的资料
      </p>
      <EntityList
        entities={data.list.map(toKnowledgeSummary)}
        version={version.slug}
        from={listParameters(page).toString()}
        emptyMessage={
          data.pagination.total > 0
            ? '这一页没有结果，可返回第一页查看。'
            : '没有找到符合条件的条目，试试更短的名称或地点。'
        }
      />
      {data.pagination.totalPages > 1 && (
        <nav
          aria-label="百科分页"
          className="mt-5 flex items-center justify-between gap-3 text-sm"
        >
          {data.pagination.hasPrev ? (
            <Link
              href={href(page - 1)}
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
              href={href(page + 1)}
              className="inline-flex min-h-11 items-center px-3 underline"
            >
              下一页
            </Link>
          ) : (
            <span />
          )}
        </nav>
      )}
      {data.pagination.total > 0 && data.list.length === 0 && (
        <Link
          href={href(1)}
          className="mt-4 inline-flex min-h-11 items-center text-sm underline"
        >
          返回第一页
        </Link>
      )}
    </div>
  )
}
