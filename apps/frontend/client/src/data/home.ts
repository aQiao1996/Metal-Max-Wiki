import { getEquipmentEntries } from '@/data/equipment/catalog'
import { getKnowledgeEntries } from '@/data/knowledge/catalog'
import { toKnowledgeSummary } from '@/data/knowledge/entry'
import type { WikiEntitySummary } from '@/types/wiki'
import { guides } from '@/data/guides'
import { equipmentTypeById } from '@/config/equipment-types'

const equipmentEntities: WikiEntitySummary[] = getEquipmentEntries()
  .slice(0, 2)
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
export const recentEntities: WikiEntitySummary[] = [
  ...getKnowledgeEntries('wanted-monsters').slice(0, 2).map(toKnowledgeSummary),
  ...equipmentEntities,
]
export const featuredEntity = recentEntities[0]
export const recentGuides = guides.slice(0, 2)
