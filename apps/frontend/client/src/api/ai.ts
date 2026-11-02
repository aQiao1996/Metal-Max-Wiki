import { z } from 'zod'

import { request } from '@/lib/request'
import type { GameVersionSlug } from '@/config/game-versions'

const sourceSchema = z.object({
  number: z.number().int().positive(),
  title: z.string(),
  href: z.string().regex(/^\/v\/[a-z0-9-]+\/wiki\/equipment\/[a-z0-9-]+$/),
  excerpt: z.string(),
  verificationStatus: z.enum(['source_only', 'compatible_candidate']),
})
const answerSchema = z.object({
  answer: z.string(),
  sources: z.array(sourceSchema),
  status: z.enum(['answered', 'insufficient_evidence']),
})

/** 查询模型配置状态。 */
export function getModelStatus() {
  return request(
    '/api/v1/ai/status',
    z.object({ configured: z.boolean(), model: z.string() }),
  )
}

/** 在指定版本内提问，回答和引用由同一个响应返回。 */
export function askQuestion(
  version: GameVersionSlug,
  question: string,
  signal: AbortSignal,
) {
  return request(`/api/v1/versions/${version}/ask`, answerSchema, {
    method: 'POST',
    body: JSON.stringify({ question }),
    signal,
  })
}
