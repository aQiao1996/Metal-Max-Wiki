import {
  defaultEquipmentType,
  equipmentProfessions,
  equipmentTypeById,
  equipmentTypes,
  type EquipmentProfessionId,
} from '@/config/equipment-types'
import type {
  EquipmentEntry,
  EquipmentQuery,
  EquipmentSort,
  EquipmentTypeId,
} from '@/types/equipment'

export type SearchParamValue = string | readonly string[] | undefined
export type EquipmentSearchParams = Readonly<Record<string, SearchParamValue>>

function firstValue(value: SearchParamValue): string | undefined {
  return typeof value === 'string' ? value : value?.[0]
}

function isEquipmentType(value: string | undefined): value is EquipmentTypeId {
  return equipmentTypes.some((config) => config.id === value)
}

function isProfession(value: string): value is EquipmentProfessionId {
  return equipmentProfessions.some((profession) => profession.id === value)
}

function isAllowedSort(
  value: string | undefined,
  sorts: readonly EquipmentSort[],
): value is EquipmentSort {
  return sorts.some((sort) => sort === value)
}

/** 将 URL 查询参数规范化为当前装备类型支持的查询条件。 */
export function parseEquipmentQuery(
  params: EquipmentSearchParams,
): EquipmentQuery {
  const typeValue = firstValue(params.type)
  const type = isEquipmentType(typeValue) ? typeValue : defaultEquipmentType
  const config = equipmentTypeById.get(type)

  if (config === undefined) {
    throw new Error(`装备类型缺少配置：${type}`)
  }

  const sortValue = firstValue(params.sort)
  const professionValue = firstValue(params.profession)?.trim() ?? ''
  const hasTraits = type === 'c-unit' || type === 'engine'

  return {
    type,
    q: firstValue(params.q)?.trim() ?? '',
    sort: isAllowedSort(sortValue, config.sorts) ? sortValue : 'name-asc',
    element: hasTraits ? '' : (firstValue(params.element)?.trim() ?? ''),
    trait: hasTraits ? (firstValue(params.trait)?.trim() ?? '') : '',
    profession:
      type === 'human-weapon' && isProfession(professionValue)
        ? professionValue
        : '',
  }
}

function compareNumbers(
  left: number | undefined,
  right: number | undefined,
  direction: 'asc' | 'desc',
): number {
  if (left === undefined) {
    return right === undefined ? 0 : 1
  }

  if (right === undefined) {
    return -1
  }

  return direction === 'asc' ? left - right : right - left
}

function numericAttribute(
  entry: EquipmentEntry,
  key: 'attack' | 'capacity' | 'price' | 'weight',
): number | undefined {
  const value = entry.attributes[key]
  if (typeof value === 'number') {
    return value
  }

  const rawValue = entry.attributes[`${key}_raw`]
  if (typeof rawValue !== 'string' || !/^\d+(?:\.\d+)?$/.test(rawValue)) {
    return undefined
  }

  const parsedValue = Number(rawValue)
  return Number.isFinite(parsedValue) ? parsedValue : undefined
}

/** 按规范化查询筛选并排序装备条目，不修改输入数组。 */
export function filterEquipmentEntries(
  entries: readonly EquipmentEntry[],
  query: EquipmentQuery,
): EquipmentEntry[] {
  const searchText = query.q.toLocaleLowerCase('zh-CN')
  const professionConfig =
    query.type === 'human-weapon' && isProfession(query.profession)
      ? equipmentProfessions.find(
          (profession) => profession.id === query.profession,
        )
      : undefined

  const filtered = entries.filter((entry) => {
    if (entry.type !== query.type) {
      return false
    }

    if (
      searchText !== '' &&
      !entry.searchText.toLocaleLowerCase('zh-CN').includes(searchText)
    ) {
      return false
    }

    if (
      query.element !== '' &&
      entry.attributes.element_raw !== query.element
    ) {
      return false
    }
    if (query.trait !== '' && entry.attributes.trait_name_raw !== query.trait) {
      return false
    }

    return (
      professionConfig === undefined ||
      entry.attributes[professionConfig.attribute] === '○'
    )
  })

  return filtered.sort((left, right) => {
    switch (query.sort) {
      case 'attack-desc':
        return compareNumbers(
          numericAttribute(left, 'attack'),
          numericAttribute(right, 'attack'),
          'desc',
        )
      case 'capacity-desc':
        return compareNumbers(
          numericAttribute(left, 'capacity'),
          numericAttribute(right, 'capacity'),
          'desc',
        )
      case 'price-asc':
        return compareNumbers(
          numericAttribute(left, 'price'),
          numericAttribute(right, 'price'),
          'asc',
        )
      case 'weight-asc':
        return compareNumbers(
          numericAttribute(left, 'weight'),
          numericAttribute(right, 'weight'),
          'asc',
        )
      case 'name-asc':
        return left.name.localeCompare(right.name, 'zh-CN')
    }
  })
}

/** 将查询条件序列化为仅含有效非默认项的 URL 搜索串。 */
export function buildEquipmentSearch(query: EquipmentQuery): string {
  const params = new URLSearchParams({ type: query.type })

  if (query.q !== '') {
    params.set('q', query.q)
  }

  if (query.sort !== 'name-asc') {
    params.set('sort', query.sort)
  }

  if (query.element !== '') {
    params.set('element', query.element)
  }
  if (
    (query.type === 'c-unit' || query.type === 'engine') &&
    query.trait !== ''
  ) {
    params.set('trait', query.trait)
  }

  if (query.type === 'human-weapon' && query.profession !== '') {
    params.set('profession', query.profession)
  }

  return params.toString()
}
