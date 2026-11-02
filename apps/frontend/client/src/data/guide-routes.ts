import { z } from 'zod'

import rawRoutes from '../../../../../data/interim/mm2r/0.99/guide-routes.json'

const routeIndex = z
  .object({
    schema_version: z.literal(1),
    game: z.literal('mm2r'),
    target_version: z.literal('0.99'),
    slugs: z.array(z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)).length(23),
  })
  .strict()
  .parse(rawRoutes)

export const guideSlugs: ReadonlySet<string> = new Set(routeIndex.slugs)
if (guideSlugs.size !== routeIndex.slugs.length) {
  throw new Error('攻略路径索引包含重复章节')
}
