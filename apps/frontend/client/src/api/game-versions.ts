import { z } from 'zod'

import { request } from '@/lib/request'

const versionsSchema = z.array(
  z.object({
    slug: z.enum(['mm2r-099', 'mm2r-nex', 'mm3', 'mm4']),
    game: z.string(),
    version: z.string(),
    shortLabel: z.string(),
    status: z.enum(['available', 'planned']),
  }),
)

/** 获取站点开放版本与建设中版本。 */
export function getGameVersions() {
  return request('/api/v1/game-versions', versionsSchema)
}
