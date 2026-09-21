export const gameVersions = [
  {
    slug: 'mm2r-099',
    game: '重装机兵2R',
    version: '0.99 汉化版',
    shortLabel: '2R / 0.99',
    status: 'available',
  },
  {
    slug: 'mm2r-nex',
    game: '重装机兵2R NEX',
    version: '民间改版',
    shortLabel: '2R NEX',
    status: 'planned',
  },
  {
    slug: 'mm3',
    game: '重装机兵3',
    version: '版本待定',
    shortLabel: 'MM3',
    status: 'planned',
  },
  {
    slug: 'mm4',
    game: '重装机兵4',
    version: '版本待定',
    shortLabel: 'MM4',
    status: 'planned',
  },
] as const

export type GameVersion = (typeof gameVersions)[number]
export type GameVersionSlug = GameVersion['slug']

export const defaultGameVersion = 'mm2r-099' satisfies GameVersionSlug

export function getGameVersion(slug: string): GameVersion | undefined {
  return gameVersions.find((version) => version.slug === slug)
}

export function isAvailableGameVersion(
  version: GameVersion,
): version is Extract<GameVersion, { status: 'available' }> {
  return version.status === 'available'
}
