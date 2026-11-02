import type { Metadata } from 'next'
import { Suspense } from 'react'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { ArrowLeft, Info } from 'lucide-react'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { equipmentTypeById, equipmentTypes } from '@/config/equipment-types'
import { getEquipmentEntries } from '@/data/equipment/catalog'
import {
  parseEquipmentQuery,
  type EquipmentSearchParams,
} from '@/lib/equipment-query'
import type { EquipmentTypeId } from '@/types/equipment'
import { EquipmentFilterForm } from '@/components/equipment/EquipmentFilterForm'
import { EquipmentResults } from '@/components/equipment/EquipmentResults'
import { EquipmentTypeNav } from '@/components/equipment/EquipmentTypeNav'

export const metadata: Metadata = {
  title: '装备百科',
}

interface EquipmentPageProps {
  params: Promise<{ version: string }>
  searchParams: Promise<EquipmentSearchParams>
}

export default async function EquipmentPage({
  params,
  searchParams,
}: EquipmentPageProps) {
  const [{ version: versionSlug }, rawSearchParams] = await Promise.all([
    params,
    searchParams,
  ])
  const version = getGameVersion(versionSlug)

  if (!version || !isAvailableGameVersion(version)) {
    notFound()
  }

  const entries = getEquipmentEntries()
  const query = parseEquipmentQuery(rawSearchParams)
  const config = equipmentTypeById.get(query.type)

  if (config === undefined) {
    throw new Error(`装备类型缺少配置：${query.type}`)
  }

  const counts = new Map<EquipmentTypeId, number>(
    equipmentTypes.map((type) => [type.id, 0]),
  )

  for (const entry of entries) {
    counts.set(entry.type, (counts.get(entry.type) ?? 0) + 1)
  }

  const currentTypeEntries = entries.filter(
    (entry) => entry.type === query.type,
  )
  const rawPage = Array.isArray(rawSearchParams.page)
    ? rawSearchParams.page[0]
    : rawSearchParams.page
  const page =
    rawPage && /^[1-9][0-9]{0,3}$/.test(rawPage) ? Number(rawPage) : 1
  const elements = [
    ...new Set(
      currentTypeEntries
        .map((entry) => entry.attributes.element_raw)
        .filter((value): value is string => typeof value === 'string'),
    ),
  ].sort((left, right) => left.localeCompare(right, 'zh-CN'))

  return (
    <div className="mx-auto max-w-6xl pb-10">
      <Link
        href={`/v/${version.slug}`}
        className="text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center gap-2 text-sm hover:text-[var(--mm-navy)] focus-visible:ring-2 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" />
        返回情报总览
      </Link>

      <header className="border-border mt-5 border-b pb-7">
        <p className="text-xs font-semibold tracking-[0.16em] text-[var(--mm-navy)] uppercase">
          Equipment index
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          装备百科
        </h1>
        <p className="text-foreground mt-3 max-w-3xl leading-7 text-pretty">
          {version.game} · {version.version}
          ，按装备类型检索属性、适用职业与关键数值。
        </p>
        <div className="bg-accent text-accent-foreground mt-5 flex max-w-3xl items-start gap-2.5 border-l-2 border-[var(--mm-signal)] px-3 py-3 text-sm leading-6">
          <Info className="mt-1 size-4 shrink-0" aria-hidden="true" />
          <p>
            当前收录的是 0.9 系资料整理出的 0.99 兼容候选，尚未完成逐项实机核验
          </p>
        </div>
      </header>

      <section className="pt-7" aria-labelledby="equipment-type-heading">
        <EquipmentTypeNav
          counts={counts}
          query={query}
          version={version.slug}
        />

        <div className="mt-7">
          <h2
            id="equipment-type-heading"
            className="text-xl font-semibold text-[var(--mm-navy)] sm:text-2xl"
          >
            {config.label}
          </h2>
          <p className="text-foreground mt-2 text-sm leading-6">
            {config.description}
          </p>
        </div>

        <div className="mt-5">
          <EquipmentFilterForm
            key={`${query.type}:${query.q}:${query.element}:${query.sort}:${query.profession ?? ''}`}
            elements={elements}
            query={query}
            version={version.slug}
          />
        </div>

        <Suspense
          key={`${JSON.stringify(query)}:${page}`}
          fallback={
            <p className="text-muted-foreground py-8 text-sm" role="status">
              正在读取装备资料…
            </p>
          }
        >
          <EquipmentResults version={version.slug} query={query} page={page} />
        </Suspense>
      </section>
    </div>
  )
}
