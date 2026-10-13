import { equipmentProfessions } from '@/config/equipment-types'
import {
  buildEquipmentSearch,
  parseEquipmentQuery,
} from '@/lib/equipment-query'
import type { EquipmentEntry, EquipmentNameSource } from '@/types/equipment'
import type { WikiAttribute } from '@/types/wiki'

export const equipmentNameSourceLabels = {
  zh_099: '0.99 实机名称',
  zh_09: '0.9 系汉化名称',
  ja: '日文原名',
} as const satisfies Record<EquipmentNameSource, string>

export const equipmentIssueLabels: Readonly<Record<string, string>> = {
  missing_japanese_name: '来源缺少日文原名',
  ambiguous_same_source_name: '同一来源存在重名记录',
  source_merged_cell: '原始表格包含跨列单元格',
}

const humanWeaponFields = [
  { key: 'attack_raw', label: '攻击力' },
  { key: 'range_raw', label: '范围' },
  { key: 'element_raw', label: '属性' },
  { key: 'additional_raw', label: '追加效果' },
  { key: 'price_raw', label: '价格' },
  { key: 'stars_raw', label: '星级' },
  { key: 'acquisition_raw', label: '获取方式' },
  { key: 'notes_raw', label: '备注' },
] as const

const mainCannonFields = [
  { key: 'attack_raw', label: '攻击力' },
  { key: 'defense_raw', label: '防御力' },
  { key: 'weight_raw', label: '重量' },
  { key: 'magazine_raw', label: '弹仓' },
  { key: 'range_raw', label: '范围' },
  { key: 'element_raw', label: '属性' },
  { key: 'special_shell_raw', label: '特殊炮弹' },
  { key: 'price_raw', label: '价格' },
  { key: 'rarity_raw', label: '稀有度' },
] as const

function toProfessionDisplayValue(value: string | number): string {
  if (value === '○') {
    return '可装备'
  }

  if (value === '-') {
    return '不可装备'
  }

  return String(value)
}

/** 生成详情页可展示的属性，并保留数值 0。 */
export function buildEquipmentDetailAttributes(
  entry: EquipmentEntry,
): WikiAttribute[] {
  const fields =
    entry.type === 'human-weapon' ? humanWeaponFields : mainCannonFields
  const attributes: WikiAttribute[] = []

  for (const field of fields) {
    const value = entry.attributes[field.key]

    if (value !== undefined) {
      attributes.push({ label: field.label, value: String(value) })
    }
  }

  if (entry.type === 'human-weapon') {
    for (const profession of equipmentProfessions) {
      const value = entry.attributes[profession.attribute]

      if (value !== undefined) {
        attributes.push({
          label: profession.label,
          value: toProfessionDisplayValue(value),
        })
      }
    }
  }

  return attributes
}

/** 将列表页嵌套查询收敛为当前版本内的固定返回地址。 */
export function buildEquipmentReturnHref(
  version: string,
  from?: string | readonly string[],
): string {
  const fromValue = typeof from === 'string' ? from : from?.[0]
  const rawQuery =
    fromValue === undefined
      ? {}
      : Object.fromEntries(new URLSearchParams(fromValue))
  const query = parseEquipmentQuery(rawQuery)

  return `/v/${version}/wiki/equipment?${buildEquipmentSearch(query)}`
}
