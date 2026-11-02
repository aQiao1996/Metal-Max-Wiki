import type { RawEquipmentRecord } from '@/data/equipment/schema'
import type {
  EquipmentSort,
  EquipmentTypeConfig,
  EquipmentTypeId,
} from '@/types/equipment'

interface EquipmentProfessionDefinition {
  readonly id: string
  readonly label: string
  readonly attribute: `${string}_raw`
}

export const equipmentProfessions = [
  { id: 'hunter', label: '猎人', attribute: 'hunter_raw' },
  { id: 'mechanic', label: '机械师', attribute: 'mechanic_raw' },
  { id: 'soldier', label: '战士', attribute: 'soldier_raw' },
  { id: 'nurse', label: '护士', attribute: 'nurse_raw' },
  { id: 'artist', label: '艺术家', attribute: 'artist_raw' },
  { id: 'wrestler', label: '摔跤手', attribute: 'wrestler_raw' },
] as const satisfies readonly EquipmentProfessionDefinition[]

export type EquipmentProfessionId = (typeof equipmentProfessions)[number]['id']

export const equipmentTypes = [
  {
    id: 'human-weapon',
    kind: 'human_weapon',
    label: '人类武器',
    description: '人类角色可以装备的攻击武器。',
    emptyMessage: '暂无人类武器资料。',
    sorts: ['name-asc', 'attack-desc', 'price-asc'],
  },
  {
    id: 'main-cannon',
    kind: 'main_cannon',
    label: '主炮',
    description: '战车使用的主要攻击武器。',
    emptyMessage: '暂无主炮资料。',
    sorts: ['name-asc', 'attack-desc', 'price-asc', 'weight-asc'],
  },
  {
    id: 'sub-gun',
    kind: 'sub_gun',
    label: '副炮',
    description: '查看副炮的攻击方式、弹仓、迎击适用标记与逐星级改造数值。',
    emptyMessage: '暂无副炮资料。',
    sorts: ['name-asc', 'attack-desc', 'weight-asc', 'price-asc'],
  },
  {
    id: 'special-equipment',
    kind: 'special_equipment',
    label: 'S-E',
    description: '特殊武器、迎击装备与逐星级改造资料。',
    emptyMessage: '暂无 S-E 资料。',
    sorts: ['name-asc', 'attack-desc', 'price-asc', 'weight-asc'],
  },
  {
    id: 'c-unit',
    kind: 'c_unit',
    label: 'C装置',
    description: '按特性选择控制装置，查看主动指令、被动效果与逐星级改造数值。',
    emptyMessage: '暂无 C 装置资料。',
    sorts: ['name-asc', 'weight-asc', 'price-asc'],
  },
  {
    id: 'engine',
    kind: 'engine',
    label: '引擎',
    description: '查看基础载重、特性条件、逐星级数值与马力强化路径。',
    emptyMessage: '暂无引擎资料。',
    sorts: ['name-asc', 'capacity-desc', 'weight-asc', 'price-asc'],
  },
] as const satisfies readonly EquipmentTypeConfig[]

export const defaultEquipmentType = 'human-weapon' satisfies EquipmentTypeId

export const legacyEquipmentDetailIds: ReadonlyMap<string, string> = new Map([
  ['main-cannons/universe-cannon', 'main-cannon-7972064880'],
  ['special-equipment/ddt-rain', 'special-equipment-dc7dec0d83'],
])

export const equipmentTypeById = new Map<EquipmentTypeId, EquipmentTypeConfig>(
  equipmentTypes.map((config): [EquipmentTypeId, EquipmentTypeConfig] => [
    config.id,
    config,
  ]),
)

type EquipmentKind = RawEquipmentRecord['kind']
type ConfiguredEquipmentType = EquipmentTypeConfig & { kind: EquipmentKind }

const equipmentTypeConfigs: readonly EquipmentTypeConfig[] = equipmentTypes
const configuredEquipmentTypes = equipmentTypeConfigs.filter(
  (config): config is ConfiguredEquipmentType => config.kind !== null,
)

export const equipmentTypeByKind = new Map<
  EquipmentKind,
  ConfiguredEquipmentType
>(configuredEquipmentTypes.map((config) => [config.kind, config]))

interface LegacyEquipmentCategoryDefinition {
  readonly categorySlug: string
  readonly typeId: EquipmentTypeId
}

export const legacyEquipmentCategories = [
  { categorySlug: 'main-cannons', typeId: 'main-cannon' },
  { categorySlug: 'sub-guns', typeId: 'sub-gun' },
  { categorySlug: 'special-equipment', typeId: 'special-equipment' },
  { categorySlug: 'c-units', typeId: 'c-unit' },
  { categorySlug: 'engines', typeId: 'engine' },
] as const satisfies readonly LegacyEquipmentCategoryDefinition[]

export type LegacyEquipmentCategorySlug =
  (typeof legacyEquipmentCategories)[number]['categorySlug']

const legacyEquipmentTypeByCategory = new Map<string, EquipmentTypeId>(
  legacyEquipmentCategories.map(
    ({ categorySlug, typeId }): [string, EquipmentTypeId] => [
      categorySlug,
      typeId,
    ],
  ),
)

/** 将旧百科分类转换为合并后的装备类型。 */
export function getLegacyEquipmentType(
  categorySlug: string,
): EquipmentTypeId | undefined {
  return legacyEquipmentTypeByCategory.get(categorySlug)
}

export const equipmentSortLabels = {
  'name-asc': '名称升序',
  'attack-desc': '攻击力降序',
  'capacity-desc': '基础载重降序',
  'price-asc': '价格升序',
  'weight-asc': '重量升序',
} as const satisfies Record<EquipmentSort, string>
