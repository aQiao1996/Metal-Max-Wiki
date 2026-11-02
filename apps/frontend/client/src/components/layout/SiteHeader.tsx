import type { GameVersion } from '@/config/game-versions'
import { AccountMenu } from '@/components/auth/AccountMenu'

import { GlobalSearchDialog } from '../search/GlobalSearchDialog'

interface SiteHeaderProps {
  version: GameVersion
}

export function SiteHeader({ version }: SiteHeaderProps) {
  return (
    <header className="border-border bg-background/92 sticky top-0 z-30 hidden h-16 items-center gap-4 border-b px-7 backdrop-blur md:flex lg:px-10">
      <GlobalSearchDialog version={version} />
      <div className="ml-auto flex items-center gap-3">
        <p className="text-muted-foreground hidden text-xs xl:block">
          当前资料范围：{version.game} · {version.version}
        </p>
        <AccountMenu />
      </div>
    </header>
  )
}
