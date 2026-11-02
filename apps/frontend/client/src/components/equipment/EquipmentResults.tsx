import Link from 'next/link'

import { equipmentPageSchema } from '@/api/equipment'
import { equipmentTypeById } from '@/config/equipment-types'
import type { GameVersionSlug } from '@/config/game-versions'
import { buildEquipmentSearch } from '@/lib/equipment-query'
import { serverRequest } from '@/lib/request/server'
import type { EquipmentQuery } from '@/types/equipment'
import { EquipmentList } from './EquipmentList'

export async function EquipmentResults({
  version,
  query,
  page,
}: {
  version: GameVersionSlug
  query: EquipmentQuery
  page: number
}) {
  const params = new URLSearchParams(buildEquipmentSearch(query))
  params.set('page', String(page))
  const data = await serverRequest(
    `/versions/${version}/equipment?${params}`,
    equipmentPageSchema,
  )
  const config = equipmentTypeById.get(query.type)
  if (!config) throw new Error('装备类型未配置')
  const pageHref = (number: number) =>
    `/v/${version}/wiki/equipment?${buildEquipmentSearch(query)}&page=${number}`
  return (
    <>
      <p className="mt-6 mb-3 text-sm font-medium text-[var(--mm-navy)]">
        共 {data.pagination.total} 条符合条件的装备
      </p>
      <EquipmentList
        emptyMessage={config.emptyMessage}
        entries={data.list}
        query={query}
        totalForType={data.typeCounts[query.type]}
        version={version}
        page={page}
      />
      {data.pagination.totalPages > 1 && (
        <nav
          aria-label="装备分页"
          className="border-border mt-6 flex items-center justify-between gap-3 border-t pt-4 text-sm"
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
    </>
  )
}
