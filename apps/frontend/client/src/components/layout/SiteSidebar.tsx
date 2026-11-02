'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { Bot, BookOpenText, Compass, ScrollText } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import { cn } from '@/lib/utils'

import { VersionSwitcher } from './VersionSwitcher'

export const siteNavigationItems = [
  { label: '情报总览', href: '', activePrefix: '', icon: Compass },
  {
    label: '资料百科',
    href: '/wiki/equipment',
    activePrefix: '/wiki',
    icon: BookOpenText,
  },
  {
    label: '攻略整理',
    href: '/guides',
    activePrefix: '/guides',
    icon: ScrollText,
  },
  { label: 'AI 问答', href: '/ai', activePrefix: '/ai', icon: Bot },
] as const

type SiteNavigationItem = (typeof siteNavigationItems)[number]

/** 按当前版本与导航前缀判断主导航活动态。 */
export function isSiteNavigationItemActive(
  pathname: string,
  version: GameVersion['slug'],
  item: SiteNavigationItem,
): boolean {
  const activePath = buildVersionPath(version, item.activePrefix)

  if (item.activePrefix === '') {
    return pathname === activePath
  }

  return pathname === activePath || pathname.startsWith(`${activePath}/`)
}

interface SiteSidebarProps {
  version: GameVersion
}

export function SiteSidebar({ version }: SiteSidebarProps) {
  const pathname = usePathname()

  return (
    <aside className="text-sidebar-foreground fixed inset-y-0 left-0 z-40 hidden w-56 flex-col bg-[var(--mm-navy)] md:flex">
      <div className="border-b border-white/10 px-5 py-6">
        <Link
          href={buildVersionPath(version.slug)}
          className="focus-visible:ring-sidebar-ring block focus-visible:ring-2 focus-visible:outline-none"
        >
          <span className="block text-[11px] font-semibold tracking-[0.22em] text-white/55">
            METAL MAX
          </span>
          <span className="mt-1 block text-xl font-semibold tracking-tight text-white">
            资料库
          </span>
        </Link>
      </div>

      <div className="px-3 py-4">
        <VersionSwitcher currentVersion={version} inverted />
      </div>

      <nav className="flex-1 px-3" aria-label="主导航">
        <p className="px-3 pt-2 pb-2 text-[10px] font-medium tracking-[0.16em] text-white/40 uppercase">
          Explore
        </p>
        <ul className="space-y-1">
          {siteNavigationItems.map((item) => {
            const href = buildVersionPath(version.slug, item.href)
            const isActive = isSiteNavigationItemActive(
              pathname,
              version.slug,
              item,
            )
            const Icon = item.icon

            return (
              <li key={item.href}>
                <Link
                  href={href}
                  className={cn(
                    'focus-visible:ring-sidebar-ring flex min-h-10 items-center gap-3 rounded-md px-3 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none',
                    isActive
                      ? 'bg-white/12 text-white'
                      : 'text-white/68 hover:bg-white/[0.07] hover:text-white',
                  )}
                >
                  <Icon className="size-[17px]" strokeWidth={1.8} />
                  <span>{item.label}</span>
                  {item.href === '/ai' && (
                    <span className="ml-auto size-1.5 rounded-full bg-[var(--mm-signal)]" />
                  )}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="border-t border-white/10 px-5 py-4 text-xs leading-5 text-white/40">
        社区资料库
      </div>
    </aside>
  )
}
