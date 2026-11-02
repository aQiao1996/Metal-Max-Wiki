import type { RawEquipmentRecord } from '@/data/equipment/schema'

export const equipmentTypeIds = [
  'human-weapon',
  'main-cannon',
  'sub-gun',
  'special-equipment',
  'c-unit',
  'engine',
] as const

export type EquipmentTypeId = (typeof equipmentTypeIds)[number]
export type EquipmentNameSource = 'zh_099' | 'zh_09' | 'zh_reference' | 'ja'
export type EquipmentSort =
  'name-asc' | 'attack-desc' | 'capacity-desc' | 'price-asc' | 'weight-asc'

export interface EquipmentEntry extends RawEquipmentRecord {
  type: EquipmentTypeId
  name: string
  nameSource: EquipmentNameSource
  searchText: string
}

export interface EquipmentQuery {
  type: EquipmentTypeId
  q: string
  sort: EquipmentSort
  element: string
  trait: string
  profession: string
}

export interface EquipmentTypeConfig {
  id: EquipmentTypeId
  kind: RawEquipmentRecord['kind'] | null
  label: string
  description: string
  emptyMessage: string
  sorts: readonly EquipmentSort[]
}
