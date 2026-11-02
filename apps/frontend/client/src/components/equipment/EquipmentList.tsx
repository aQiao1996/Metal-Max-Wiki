import Link from 'next/link'

import { ArrowRight } from 'lucide-react'

import type { GameVersionSlug } from '@/config/game-versions'
import { buildEquipmentSearch } from '@/lib/equipment-query'
import type { EquipmentEntry, EquipmentQuery } from '@/types/equipment'

import { EquipmentVerificationBadge } from './EquipmentVerificationBadge'

interface EquipmentListProps {
  emptyMessage: string
  entries: readonly EquipmentEntry[]
  query: EquipmentQuery
  totalForType: number
  version: GameVersionSlug
  page?: number
}

const humanWeaponFields = [
  { key: 'attack_raw', label: '攻击力' },
  { key: 'range_raw', label: '攻击范围' },
  { key: 'element_raw', label: '属性' },
] as const

const mainCannonFields = [
  { key: 'attack_raw', label: '攻击力' },
  { key: 'weight_raw', label: '重量' },
  { key: 'magazine_raw', label: '弹仓' },
] as const

const cUnitFields = [
  { key: 'trait_name_raw', label: '特性' },
  { key: 'trait_activation_raw', label: '生效方式' },
  { key: 'weight_raw', label: '重量（t）' },
] as const

const engineFields = [
  { key: 'capacity_raw', label: '基础载重（t）' },
  { key: 'trait_name_raw', label: '特性' },
  { key: 'weight_raw', label: '重量（t）' },
] as const

export function EquipmentList({
  emptyMessage,
  entries,
  query,
  totalForType,
  version,
  page = 1,
}: EquipmentListProps) {
  const equipmentIndexPath = `/v/${version}/wiki/equipment`

  if (totalForType === 0) {
    return (
      <div className="border-border text-foreground border-y py-10 text-center text-sm">
        {emptyMessage}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className="border-border border-y py-10 text-center">
        <p className="text-foreground text-sm">没有找到符合当前条件的装备。</p>
        <Link
          href={`${equipmentIndexPath}?type=${query.type}`}
          className="text-accent-foreground focus-visible:ring-ring mt-4 inline-flex min-h-10 items-center text-sm font-medium underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          清空筛选条件
        </Link>
      </div>
    )
  }

  const from = new URLSearchParams(buildEquipmentSearch(query))
  if (page > 1) from.set('page', String(page))
  const encodedFrom = encodeURIComponent(from.toString())

  return (
    <ul className="border-border border-t">
      {entries.map((entry) => {
        const fields =
          entry.type === 'human-weapon'
            ? humanWeaponFields
            : entry.type === 'c-unit'
              ? cUnitFields
              : entry.type === 'engine'
                ? engineFields
                : mainCannonFields
        const japaneseName =
          entry.names.ja !== null && entry.names.ja !== entry.name
            ? entry.names.ja
            : null

        return (
          <li key={entry.id}>
            <Link
              href={`${equipmentIndexPath}/${encodeURIComponent(entry.id)}?from=${encodedFrom}`}
              className="group border-border focus-visible:ring-ring grid min-w-0 gap-4 border-b py-5 transition-colors hover:bg-white/55 focus-visible:ring-2 focus-visible:outline-none sm:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,0.5fr))_1rem] sm:items-center sm:gap-5 sm:px-3"
            >
              <span className="min-w-0">
                <span className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="min-w-0 font-medium break-words text-[var(--mm-navy)]">
                    {entry.name}
                  </span>
                  <EquipmentVerificationBadge
                    status={entry.verification_status}
                  />
                </span>
                {japaneseName !== null && (
                  <span className="mt-1 block text-xs break-words text-[var(--mm-navy)]">
                    日文名：{japaneseName}
                  </span>
                )}
                {(entry.type === 'special-equipment' ||
                  entry.type === 'sub-gun' ||
                  entry.type === 'c-unit' ||
                  entry.type === 'engine') &&
                  entry.attributes.stat_condition_raw !== undefined && (
                    <span className="text-muted-foreground mt-1 block text-xs leading-5">
                      {String(entry.attributes.stat_condition_raw)}
                    </span>
                  )}
                {entry.attributes.availability_raw !== undefined && (
                  <span className="text-muted-foreground mt-1 block text-xs leading-5">
                    {String(entry.attributes.availability_raw)}
                  </span>
                )}
              </span>

              <dl className="grid min-w-0 grid-cols-3 gap-3 sm:contents">
                {fields.map((field) => {
                  const value = entry.attributes[field.key]

                  return (
                    <div key={field.key} className="min-w-0">
                      <dt className="text-[0.6875rem] text-[var(--mm-navy)]">
                        {field.label}
                      </dt>
                      <dd className="mt-1 text-sm font-medium break-words">
                        {value === undefined ? '—' : String(value)}
                      </dd>
                    </div>
                  )
                })}
              </dl>

              <ArrowRight className="text-muted-foreground group-hover:text-foreground hidden size-4 transition-transform group-hover:translate-x-1 sm:block" />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
