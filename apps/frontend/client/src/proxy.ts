import { type NextRequest, NextResponse } from 'next/server'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { equipmentTypeById } from '@/config/equipment-types'
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
  if (normalizedCategory(categorySegment) !== 'equipment') {
    return NextResponse.next()
  }

  const version = getGameVersion(versionSlug)
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
