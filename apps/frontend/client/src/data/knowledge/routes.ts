import { z } from 'zod'

import rawRouteIndex from '../../../../../../data/interim/mm2r/0.99/knowledge-routes.json'

import { knowledgeCategorySchema } from './schema'

const routeSchema = z
  .object({
    category: knowledgeCategorySchema,
    id: z.string().regex(/^[a-z0-9-]+-[0-9a-f]{10}$/),
    legacy_slugs: z.array(z.string().regex(/^[a-z0-9-]+$/)),
  })
  .strict()
const index = z
  .object({
    schema_version: z.literal(1),
    game: z.literal('mm2r'),
    target_version: z.literal('0.99'),
    routes: z.array(routeSchema),
  })
  .strict()
  .parse(rawRouteIndex)

const routeIds = new Map<string, Set<string>>()
const legacyRoutes = new Map<string, { category: string; id: string }>()
const paths = new Set<string>()
for (const route of index.routes) {
  for (const slug of [route.id, ...route.legacy_slugs]) {
    const path = `${route.category}/${slug}`
    if (paths.has(path)) throw new Error(`百科路径索引存在重复地址：${path}`)
    paths.add(path)
  }
  const ids = routeIds.get(route.category) ?? new Set<string>()
  ids.add(route.id)
  routeIds.set(route.category, ids)
  for (const slug of route.legacy_slugs)
    legacyRoutes.set(`${route.category}/${slug}`, {
      category: route.category,
      id: route.id,
    })
}

export const knowledgeRouteIds: ReadonlyMap<
  string,
  ReadonlySet<string>
> = routeIds
export const legacyKnowledgeRoutes: ReadonlyMap<
  string,
  Readonly<{ category: string; id: string }>
> = legacyRoutes
