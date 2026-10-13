import rawEquipmentDataset from '../../../../../../data/interim/mm2r/0.99/equipment.json'

import { equipmentTypeByKind } from '@/config/equipment-types'
import type { EquipmentEntry, EquipmentNameSource } from '@/types/equipment'

import {
  equipmentDatasetSchema,
  type EquipmentDataset,
  type RawEquipmentRecord,
} from './schema'

/** 校验外部装备数据并拒绝重复的稳定 ID。 */
export function parseEquipmentDataset(input: unknown): EquipmentDataset {
  const dataset = equipmentDatasetSchema.parse(input)
  const ids = new Set<string>()

  for (const record of dataset.records) {
    if (ids.has(record.id)) {
      throw new Error(`装备数据包含重复 ID：${record.id}`)
    }

    ids.add(record.id)
  }

  return dataset
}

const equipmentDataset = parseEquipmentDataset(rawEquipmentDataset)

function resolveEquipmentName(record: RawEquipmentRecord): {
  name: string
  nameSource: EquipmentNameSource
} {
  if (record.names.zh_099 !== null) {
    return { name: record.names.zh_099, nameSource: 'zh_099' }
  }

  if (record.names.zh_09 !== null) {
    return { name: record.names.zh_09, nameSource: 'zh_09' }
  }

  if (record.names.ja !== null) {
    return { name: record.names.ja, nameSource: 'ja' }
  }

  throw new Error(`装备记录缺少可显示名称：${record.id}`)
}

const searchableAttributeKeys = [
  'acquisition_raw',
  'additional_raw',
  'notes_raw',
] as const

/** 将通过校验的原始记录转换为可展示、可搜索的装备条目。 */
export function toEquipmentEntry(record: RawEquipmentRecord): EquipmentEntry {
  const typeConfig = equipmentTypeByKind.get(record.kind)

  if (typeConfig === undefined) {
    throw new Error(`装备类型未配置：${record.kind}（${record.id}）`)
  }

  const { name, nameSource } = resolveEquipmentName(record)
  const searchableAttributes = searchableAttributeKeys
    .map((key) => record.attributes[key])
    .filter((value): value is string => typeof value === 'string')
  const searchText = [
    name,
    record.names.ja,
    record.names.zh_09,
    record.names.zh_099,
    ...record.names.aliases,
    ...searchableAttributes,
  ]
    .filter((value): value is string => value !== null)
    .join(' ')
    .toLocaleLowerCase('zh-CN')

  return {
    ...record,
    type: typeConfig.id,
    name,
    nameSource,
    searchText,
  }
}

const equipmentCatalog = equipmentDataset.records.map(toEquipmentEntry)

/** 返回通过边界校验的原始装备记录。 */
export function getEquipmentCatalog(): readonly RawEquipmentRecord[] {
  return equipmentDataset.records
}

/** 返回全部已转换的装备条目。 */
export function getEquipmentEntries(): readonly EquipmentEntry[] {
  return equipmentCatalog
}

/** 按稳定 ID 查找已转换的装备条目。 */
export function getEquipmentEntry(id: string): EquipmentEntry | undefined {
  return equipmentCatalog.find((entry) => entry.id === id)
}
