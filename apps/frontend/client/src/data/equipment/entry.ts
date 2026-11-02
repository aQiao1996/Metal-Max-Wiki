import { equipmentTypeByKind } from '@/config/equipment-types'
import type { EquipmentEntry, EquipmentNameSource } from '@/types/equipment'
import type { RawEquipmentRecord } from './schema'

/** 将单条资料转换为展示模型，不引入整份目录。 */
export function toEquipmentEntry(record: RawEquipmentRecord): EquipmentEntry {
  const typeConfig = equipmentTypeByKind.get(record.kind)
  if (!typeConfig)
    throw new Error(`装备类型未配置：${record.kind}（${record.id}）`)
  const nameSource: EquipmentNameSource | undefined =
    record.names.zh_099 !== null
      ? 'zh_099'
      : record.names.zh_09 !== null
        ? 'zh_09'
        : record.names.zh_reference
          ? 'zh_reference'
          : record.names.ja !== null
            ? 'ja'
            : undefined
  if (!nameSource) throw new Error(`装备记录缺少可显示名称：${record.id}`)
  const name = record.names[nameSource]
  if (name === null || name === undefined)
    throw new Error(`装备名称为空：${record.id}`)
  const values = ['acquisition_raw', 'additional_raw', 'notes_raw']
    .map((key) => record.attributes[key])
    .filter((value): value is string => typeof value === 'string')
  return {
    ...record,
    name,
    nameSource,
    type: typeConfig.id,
    searchText: [
      name,
      record.names.ja,
      record.names.zh_09,
      record.names.zh_099,
      record.names.zh_reference ?? null,
      ...record.names.aliases,
      ...values,
    ]
      .filter((value): value is string => value !== null)
      .join(' ')
      .toLocaleLowerCase('zh-CN'),
  }
}
