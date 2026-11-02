import rawEquipmentDataset from '../../../../../../data/interim/mm2r/0.99/equipment.json'

import type { EquipmentEntry } from '@/types/equipment'
import { toEquipmentEntry } from './entry'
import { applyVerifiedNames } from './verified-names'

export { toEquipmentEntry } from './entry'

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

const equipmentCatalog = applyVerifiedNames(equipmentDataset.records).map(
  toEquipmentEntry,
)

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
