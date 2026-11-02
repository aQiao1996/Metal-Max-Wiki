import { type NextRequest, NextResponse } from 'next/server'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import {
  equipmentTypeById,
  legacyEquipmentDetailIds,
} from '@/config/equipment-types'
import { getEquipmentEntry } from '@/data/equipment/catalog'

const wikiRoutePattern = /^\/v\/([^/]+)\/wiki\/([^/]+)(?:\/([^/]+))?\/?$/

function normalizedCategory(segment: string): string | undefined {
  try {
    return decodeURIComponent(segment).toLowerCase()
  } catch {
    return undefined
  }
}

export function proxy(request: NextRequest) {
  const match = wikiRoutePattern.exec(request.nextUrl.pathname)

  if (match === null) {
    return NextResponse.next()
  }

  const [, versionSlug, categorySegment, id] = match
  const version = getGameVersion(versionSlug)
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
  matcher: ['/v/:version/wiki/:category', '/v/:version/wiki/:category/:id'],
}
