import Link from 'next/link'

import type { GameVersionSlug } from '@/config/game-versions'
import {
  equipmentProfessions,
  equipmentSortLabels,
  equipmentTypeById,
} from '@/config/equipment-types'
import type { EquipmentQuery } from '@/types/equipment'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatSpecialEquipmentValue } from '@/data/equipment/special-equipment'

interface EquipmentFilterFormProps {
  elements: readonly string[]
  traits: readonly string[]
  query: EquipmentQuery
  version: GameVersionSlug
}

const controlClassName =
  'border-input bg-card focus-visible:border-ring focus-visible:ring-ring/40 h-10 w-full min-w-0 rounded-md border px-3 text-sm outline-none focus-visible:ring-2'

export function EquipmentFilterForm({
  elements,
  traits,
  query,
  version,
}: EquipmentFilterFormProps) {
  const config = equipmentTypeById.get(query.type)

  if (config === undefined) {
    throw new Error(`装备类型缺少配置：${query.type}`)
  }

  const action = `/v/${version}/wiki/equipment`
  const hasTraits = query.type === 'c-unit' || query.type === 'engine'

  return (
    <form
      action={action}
      method="get"
      className="border-border bg-card grid min-w-0 gap-4 border-y px-4 py-5 sm:grid-cols-2 sm:px-5 lg:grid-cols-4"
    >
      <input type="hidden" name="type" value={query.type} />

      <div className="min-w-0 sm:col-span-2 lg:col-span-1">
        <label
          htmlFor="equipment-query"
          className="mb-1.5 block text-xs font-medium text-[var(--mm-navy)]"
        >
          搜索装备
        </label>
        <Input
          id="equipment-query"
          maxLength={100}
          type="search"
          name="q"
          defaultValue={query.q}
          placeholder="名称、别名或获取方式"
          className="h-10 rounded-md bg-white px-3 placeholder:text-[var(--mm-navy)]"
        />
      </div>

      <div className="min-w-0">
        <label
          htmlFor={hasTraits ? 'equipment-trait' : 'equipment-element'}
          className="mb-1.5 block text-xs font-medium text-[var(--mm-navy)]"
        >
          {hasTraits ? '特性' : '属性'}
        </label>
        <select
          id={hasTraits ? 'equipment-trait' : 'equipment-element'}
          name={hasTraits ? 'trait' : 'element'}
          defaultValue={hasTraits ? query.trait : query.element}
          className={controlClassName}
        >
          <option value="">{hasTraits ? '全部特性' : '全部属性'}</option>
          {(hasTraits ? traits : elements).map((element) => (
            <option key={element} value={element}>
              {query.type === 'special-equipment' &&
              formatSpecialEquipmentValue('element_raw', element) !== element
                ? `${formatSpecialEquipmentValue('element_raw', element)}（${element}）`
                : element}
            </option>
          ))}
        </select>
      </div>

      <div className="min-w-0">
        <label
          htmlFor="equipment-sort"
          className="mb-1.5 block text-xs font-medium text-[var(--mm-navy)]"
        >
          排序
        </label>
        <select
          id="equipment-sort"
          name="sort"
          defaultValue={query.sort}
          className={controlClassName}
        >
          {config.sorts.map((sort) => (
            <option key={sort} value={sort}>
              {equipmentSortLabels[sort]}
            </option>
          ))}
        </select>
      </div>

      {query.type === 'human-weapon' && (
        <div className="min-w-0">
          <label
            htmlFor="equipment-profession"
            className="mb-1.5 block text-xs font-medium text-[var(--mm-navy)]"
          >
            可用职业
          </label>
          <select
            id="equipment-profession"
            name="profession"
            defaultValue={query.profession}
            className={controlClassName}
          >
            <option value="">全部职业</option>
            {equipmentProfessions.map((profession) => (
              <option key={profession.id} value={profession.id}>
                {profession.label}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="flex min-w-0 flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-4">
        <Button
          type="submit"
          className="min-h-11 rounded-md bg-[var(--mm-navy)] px-4 text-white hover:bg-[var(--mm-navy-deep)]"
        >
          应用条件
        </Button>
        <Link
          href={`${action}?type=${query.type}`}
          className="border-border bg-card hover:bg-muted focus-visible:ring-ring inline-flex min-h-11 items-center rounded-md border px-4 text-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
        >
          清空条件
        </Link>
      </div>
    </form>
  )
}
