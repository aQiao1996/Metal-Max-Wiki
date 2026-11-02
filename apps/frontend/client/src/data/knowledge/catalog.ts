import rawWantedDataset from '../../../../../../data/interim/mm2r/0.99/wanted-monsters.json'
import rawVehicleDataset from '../../../../../../data/interim/mm2r/0.99/vehicles.json'

import { toKnowledgeEntry, type KnowledgeEntry } from './entry'
import { knowledgeDatasetSchema, type KnowledgeCategory } from './schema'
import { knowledgeRouteIds } from './routes'

const datasets = [
  knowledgeDatasetSchema.parse(rawWantedDataset),
  knowledgeDatasetSchema.parse(rawVehicleDataset),
]
const entries: KnowledgeEntry[] = datasets.flatMap((dataset) =>
  dataset.records.map((record) => toKnowledgeEntry(record)),
)

const routeCount = [...knowledgeRouteIds.values()].reduce(
  (total, ids) => total + ids.size,
  0,
)
if (
  routeCount !== entries.length ||
  entries.some((entry) => !knowledgeRouteIds.get(entry.category)?.has(entry.id))
) {
  throw new Error('百科路径索引与真实条目不一致，请重建资料')
}

/** 返回通过边界校验的百科条目。 */
export function getKnowledgeEntries(
  category?: KnowledgeCategory,
): readonly KnowledgeEntry[] {
  return category
    ? entries.filter((entry) => entry.category === category)
    : entries
}

/** 按分类和稳定 ID 查找真实条目。 */
export function getKnowledgeEntry(
  category: KnowledgeCategory,
  id: string,
): KnowledgeEntry | undefined {
  return entries.find((entry) => entry.category === category && entry.id === id)
}
