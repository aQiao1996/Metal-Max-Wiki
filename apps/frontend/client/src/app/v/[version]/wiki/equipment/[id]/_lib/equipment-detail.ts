import { equipmentProfessions } from '@/config/equipment-types'
import {
  buildEquipmentSearch,
  parseEquipmentQuery,
} from '@/lib/equipment-query'
import type { EquipmentEntry, EquipmentNameSource } from '@/types/equipment'
import type { WikiAttribute } from '@/types/wiki'
import { formatVehicleWeaponValue } from '@/data/equipment/vehicle-weapons'

export const equipmentNameSourceLabels = {
  zh_099: '0.99 实机名称',
  zh_09: '0.9 系汉化名称',
  zh_reference: '中文参考译名（未经 0.99 实机核对）',
  ja: '日文原名',
} as const satisfies Record<EquipmentNameSource, string>

export const equipmentIssueLabels: Readonly<Record<string, string>> = {
  missing_japanese_name: '来源缺少日文原名',
  ambiguous_same_source_name: '同一来源存在重名记录',
  source_merged_cell: '原始表格包含跨列单元格',
  source_detail_unavailable: '来源尚未提供独立详情',
  source_modification_unavailable: '来源尚未提供完整改造数值',
  source_value_difference:
    '总表与独立详情存在同星级数值差异，展示值取自独立详情，仍待核对',
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

const specialEquipmentFields = [
  { key: 'stat_condition_raw', label: '数值条件' },
  { key: 'attack_raw', label: '初始攻击力' },
  { key: 'attack_max_raw', label: '普通改造攻击上限' },
  { key: 'defense_raw', label: '初始防御力' },
  { key: 'weight_raw', label: '初始重量（t）' },
  { key: 'magazine_raw', label: '初始弹仓' },
  { key: 'range_raw', label: '攻击方式' },
  { key: 'element_raw', label: '属性' },
  { key: 'interception_raw', label: '迎击兵装化' },
  { key: 'interception_note_raw', label: '迎击说明' },
  { key: 'rarity_raw', label: '可获取星级' },
  { key: 'acquisition_raw', label: '获取方式' },
  { key: 'acquisition_ja_raw', label: '获取地点原始记录（日文）' },
  { key: 'notes_raw', label: '特殊作用' },
  { key: 'source_difference_raw', label: '来源数值差异（待核对）' },
] as const

const cUnitFields = [
  { key: 'stat_condition_raw', label: '数值条件' },
  { key: 'trait_name_raw', label: '特性（中文参考）' },
  { key: 'trait_raw', label: '特性原名' },
  { key: 'trait_activation_raw', label: '生效方式' },
  { key: 'trait_effect_raw', label: '特性作用' },
  { key: 'trait_limits_raw', label: '生效限制' },
  { key: 'accuracy_raw', label: '初始命中（面板）' },
  { key: 'evasion_raw', label: '初始回避（面板）' },
  { key: 'defense_raw', label: '初始防御力' },
  { key: 'weight_raw', label: '初始重量（t）' },
  { key: 'price_raw', label: '价格（* 为卖价）' },
  { key: 'rarity_raw', label: '可获取星级' },
  { key: 'availability_raw', label: '获取限制' },
  { key: 'acquisition_raw', label: '获取方式' },
  { key: 'acquisition_ja_raw', label: '获取地点原始记录（日文）' },
  { key: 'mechanics_note_raw', label: '命中与回避说明' },
  { key: 'notes_raw', label: '使用备注' },
  { key: 'source_difference_raw', label: '来源数值差异（待核对）' },
] as const

const engineFields = [
  { key: 'stat_condition_raw', label: '数值条件' },
  { key: 'capacity_raw', label: '当前型号基础载重（t）' },
  { key: 'capacity_note_raw', label: '载重说明' },
  { key: 'trait_name_raw', label: '特性（中文参考）' },
  { key: 'trait_raw', label: '特性原名' },
  { key: 'trait_activation_raw', label: '生效方式' },
  { key: 'trait_effect_raw', label: '特性作用' },
  { key: 'trait_limits_raw', label: '生效限制' },
  { key: 'defense_raw', label: '初始防御力' },
  { key: 'weight_raw', label: '初始重量（t）' },
  { key: 'price_raw', label: '价格（* 为卖价）' },
  { key: 'rarity_raw', label: '来源星级标记' },
  { key: 'rental_stars_raw', label: '仅见租赁装备的星级' },
  { key: 'acquisition_raw', label: '获取方式' },
  { key: 'acquisition_ja_raw', label: '获取地点原始记录（日文）' },
  { key: 'upgrade_note_raw', label: '马力强化限制' },
  { key: 'notes_raw', label: '使用备注' },
  { key: 'source_difference_raw', label: '来源数值差异（待核对）' },
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
    entry.type === 'human-weapon'
      ? humanWeaponFields
      : entry.type === 'special-equipment' || entry.type === 'sub-gun'
        ? specialEquipmentFields
        : entry.type === 'c-unit'
          ? cUnitFields
          : entry.type === 'engine'
            ? engineFields
            : mainCannonFields
  const attributes: WikiAttribute[] = []

  for (const field of fields) {
    const value = entry.attributes[field.key]

    if (
      field.key === 'rarity_raw' &&
      entry.attributes.availability_raw !== undefined
    ) {
      continue
    }

    if (value !== undefined) {
      if (
        field.key === 'acquisition_ja_raw' &&
        entry.attributes.acquisition_raw !== undefined
      )
        continue
      const displayValue =
        field.key === 'rarity_raw' &&
        typeof entry.attributes.obtainable_stars_raw === 'string'
          ? `${entry.attributes.obtainable_stars_raw.split(',').join('、')} 星（来源记录）`
          : entry.type === 'special-equipment' || entry.type === 'sub-gun'
            ? formatVehicleWeaponValue(field.key, value)
            : String(value)
      attributes.push({ label: field.label, value: displayValue })
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

  const params = new URLSearchParams(buildEquipmentSearch(query))
  const page = rawQuery.page
  if (
    typeof page === 'string' &&
    /^[1-9][0-9]{0,3}$/.test(page) &&
    Number(page) > 1
  )
    params.set('page', page)
  return `/v/${version}/wiki/equipment?${params}`
}
