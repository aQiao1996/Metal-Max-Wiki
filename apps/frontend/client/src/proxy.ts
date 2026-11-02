import { type NextRequest, NextResponse } from 'next/server'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import {
  equipmentTypeById,
  legacyEquipmentDetailIds,
} from '@/config/equipment-types'
import { getEquipmentEntry } from '@/data/equipment/catalog'
import { guideSlugs } from '@/data/guide-routes'
import {
  knowledgeRouteIds,
  legacyKnowledgeRoutes,
} from '@/data/knowledge/routes'

const wikiRoutePattern = /^\/v\/([^/]+)\/wiki\/([^/]+)(?:\/([^/]+))?\/?$/

function normalizedCategory(segment: string): string | undefined {
  try {
    return decodeURIComponent(segment).toLowerCase()
  } catch {
    return undefined
  }
}

export function proxy(request: NextRequest) {
  const guideMatch = /^\/v\/([^/]+)\/([^/]+)(?:\/([^/]+))?\/?$/.exec(
    request.nextUrl.pathname,
  )
  if (guideMatch && normalizedCategory(guideMatch[2]) === 'guides') {
    const [, versionSlug, segment, slug] = guideMatch
    const version = getGameVersion(versionSlug)
    if (
      segment !== 'guides' ||
      !version ||
      !isAvailableGameVersion(version) ||
      (slug !== undefined && !guideSlugs.has(slug))
    ) {
      const url = request.nextUrl.clone()
      url.pathname = '/_not-found'
      url.search = ''
      return NextResponse.rewrite(url, { status: 404 })
    }
    return NextResponse.next()
  }
  const match = wikiRoutePattern.exec(request.nextUrl.pathname)

  if (match === null) {
    return NextResponse.next()
  }

  const [, versionSlug, categorySegment, id] = match
  const version = getGameVersion(versionSlug)
  const knowledgeLegacy = legacyKnowledgeRoutes.get(`${categorySegment}/${id}`)
  if (version && isAvailableGameVersion(version) && knowledgeLegacy) {
    const canonicalUrl = request.nextUrl.clone()
    canonicalUrl.pathname = `/v/${version.slug}/wiki/${knowledgeLegacy.category}/${knowledgeLegacy.id}`
    canonicalUrl.search = ''
    return NextResponse.redirect(canonicalUrl, 308)
  }
  const category = normalizedCategory(categorySegment)
  const knowledgeIds = category ? knowledgeRouteIds.get(category) : undefined
  if (knowledgeIds) {
    if (
      categorySegment !== category ||
      !version ||
      !isAvailableGameVersion(version) ||
      (id !== undefined && !knowledgeIds.has(id))
    ) {
      const notFoundUrl = request.nextUrl.clone()
      notFoundUrl.pathname = '/_not-found'
      notFoundUrl.search = ''
      return NextResponse.rewrite(notFoundUrl, { status: 404 })
    }
    return NextResponse.next()
  }
  const legacyId = legacyEquipmentDetailIds.get(`${categorySegment}/${id}`)
  if (
    version &&
    isAvailableGameVersion(version) &&
    legacyId &&
    getEquipmentEntry(legacyId)
  ) {
    const canonicalUrl = request.nextUrl.clone()
    canonicalUrl.pathname = `/v/${version.slug}/wiki/equipment/${legacyId}`
    canonicalUrl.search = ''
    return NextResponse.redirect(canonicalUrl, 308)
  }
  if (normalizedCategory(categorySegment) !== 'equipment') {
    return NextResponse.next()
  }

  const entry = id === undefined ? undefined : getEquipmentEntry(id)
  const typeConfig = entry && equipmentTypeById.get(entry.type)

  if (
    categorySegment !== 'equipment' ||
    version === undefined ||
    !isAvailableGameVersion(version) ||
    (id !== undefined && (entry === undefined || typeConfig === undefined))
  ) {
    const notFoundUrl = request.nextUrl.clone()
    notFoundUrl.pathname = '/_not-found'
    notFoundUrl.search = ''

    return NextResponse.rewrite(notFoundUrl, { status: 404 })
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/v/:version/wiki/:category',
    '/v/:version/wiki/:category/:id',
    '/v/:version/:section',
    '/v/:version/:section/:slug',
  ],
}
