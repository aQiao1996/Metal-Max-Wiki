import type { GameVersionSlug } from '@/config/game-versions'

const versionPathPattern = /^\/v\/[^/]+(?=\/|$)/

/** 为指定版本构建站内地址。 */
export function buildVersionPath(
  version: GameVersionSlug,
  pathname = '',
): string {
  const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`

  if (normalizedPath === '/') {
    return `/v/${version}`
  }

  return `/v/${version}${normalizedPath}`
}

/** 仅替换地址中的版本段，无效地址则返回版本首页。 */
export function replaceVersionInPathname(
  pathname: string,
  version: GameVersionSlug,
): string {
  if (!versionPathPattern.test(pathname)) {
    return buildVersionPath(version)
  }

  return pathname.replace(versionPathPattern, `/v/${version}`)
}
