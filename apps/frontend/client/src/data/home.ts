import { getEquipmentEntries } from '@/data/equipment/catalog'
import type { WikiEntitySummary } from '@/types/wiki'
import { guides } from '@/data/guides'
import { equipmentTypeById } from '@/config/equipment-types'

export const recentEntities: WikiEntitySummary[] = getEquipmentEntries()
  .slice(0, 4)
  .map((entry) => ({
    slug: entry.id,
    category: 'equipment',
    name: entry.name,
    aliases: entry.names.aliases,
    summary: ['attack_raw', 'range_raw', 'acquisition_raw']
      .map((key) => entry.attributes[key])
      .filter((value) => value !== undefined)
      .join(' · '),
    tags: [equipmentTypeById.get(entry.type)?.label ?? '装备'],
    verification: 'pending',
  }))
export const featuredEntity = recentEntities[0]
export const recentGuides = guides.slice(0, 2)
