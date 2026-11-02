import type { GameVersionSlug } from '@/config/game-versions'
import type { KnowledgeCategory } from '@/data/knowledge/schema'
import { buildVersionPath } from '@/lib/version-routes'

/** 仅恢复列表允许的参数，外部网址不能成为返回地址。 */
export function getKnowledgeReturnHref(
  version: GameVersionSlug,
  category: KnowledgeCategory,
  from?: string | string[],
): string {
  const path = buildVersionPath(version, `/wiki/${category}`)
  const raw = Array.isArray(from) ? from[0] : from
  if (!raw || raw.length > 1000) return path
  const source = new URLSearchParams(raw)
  const parameters = new URLSearchParams()
  const q = source.get('q')?.trim()
  if (q) parameters.set('q', q.slice(0, 100))
  if (source.get('sort') === 'bounty-desc')
    parameters.set('sort', 'bounty-desc')
  const page = source.get('page')
  if (page && /^[1-9][0-9]{0,3}$/.test(page)) parameters.set('page', page)
  return parameters.size > 0 ? `${path}?${parameters}` : path
}
