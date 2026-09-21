'use client'

import Link from 'next/link'

import { Menu } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'

import { GlobalSearchDialog } from '../search/GlobalSearchDialog'
import { siteNavigationItems } from './SiteSidebar'
import { VersionSwitcher } from './VersionSwitcher'

interface MobileNavigationProps {
  version: GameVersion
}

export function MobileNavigation({ version }: MobileNavigationProps) {
  return (
    <header className="border-border bg-card/95 sticky top-0 z-40 flex h-14 items-center gap-3 border-b px-4 backdrop-blur md:hidden">
      <Sheet>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="打开导航">
            <Menu className="size-5" />
          </Button>
        </SheetTrigger>
        <SheetContent
          side="left"
          className="w-[min(88vw,21rem)] gap-0 bg-[var(--mm-navy)] text-white"
        >
          <SheetHeader className="border-b border-white/10 px-5 py-5 text-left">
            <SheetTitle className="text-white">Metal Max 资料库</SheetTitle>
            <SheetDescription className="text-white/55">
              {version.game} · {version.version}
            </SheetDescription>
          </SheetHeader>

          <div className="border-b border-white/10 p-4">
            <VersionSwitcher currentVersion={version} inverted />
          </div>

          <nav className="p-3" aria-label="移动端导航">
            <ul className="space-y-1">
              {siteNavigationItems.map((item) => {
                const Icon = item.icon

                return (
                  <li key={item.href}>
                    <SheetClose asChild>
                      <Link
                        href={buildVersionPath(version.slug, item.href)}
                        className="focus-visible:ring-sidebar-ring flex min-h-11 items-center gap-3 rounded-md px-3 text-sm text-white/72 transition-colors hover:bg-white/[0.08] hover:text-white focus-visible:ring-2 focus-visible:outline-none"
                      >
                        <Icon className="size-[18px]" />
                        {item.label}
                      </Link>
                    </SheetClose>
                  </li>
                )
              })}
            </ul>
          </nav>
        </SheetContent>
      </Sheet>

      <Link
        href={buildVersionPath(version.slug)}
        className="min-w-0 flex-1 truncate font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        Metal Max 资料库
      </Link>

      <GlobalSearchDialog version={version} compact />
    </header>
  )
}
