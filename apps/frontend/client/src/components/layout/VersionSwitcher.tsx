'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { Check, ChevronDown } from 'lucide-react'

import { gameVersions, type GameVersion } from '@/config/game-versions'
import { replaceVersionInPathname } from '@/lib/version-routes'
import { cn } from '@/lib/utils'

interface VersionSwitcherProps {
  currentVersion: GameVersion
  compact?: boolean
  inverted?: boolean
}

export function VersionSwitcher({
  currentVersion,
  compact = false,
  inverted = false,
}: VersionSwitcherProps) {
  const pathname = usePathname()

  return (
    <details className="group relative">
      <summary
        className={cn(
          'focus-visible:ring-ring flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm transition-colors marker:content-none focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden',
          inverted
            ? 'border-white/15 bg-white/[0.06] text-white hover:bg-white/10'
            : 'border-border bg-card text-foreground hover:bg-muted',
          compact ? 'w-auto min-w-32' : 'w-full',
        )}
      >
        <span className="min-w-0">
          <span className="block truncate font-medium">
            {currentVersion.shortLabel}
          </span>
          {!compact && (
            <span
              className={cn(
                'mt-0.5 block truncate text-xs',
                inverted ? 'text-white/55' : 'text-muted-foreground',
              )}
            >
              {currentVersion.version}
            </span>
          )}
        </span>
        <ChevronDown className="size-4 shrink-0 transition-transform group-open:rotate-180" />
      </summary>

      <div
        className={cn(
          'border-border bg-popover text-popover-foreground absolute z-40 mt-2 min-w-64 overflow-hidden rounded-md border p-1.5 shadow-[0_12px_32px_rgba(23,36,43,0.14)]',
          inverted ? 'left-0' : 'right-0',
        )}
      >
        <p className="text-muted-foreground px-2.5 pt-2 pb-1 text-[11px] font-medium tracking-[0.12em] uppercase">
          资料版本
        </p>
        {gameVersions.map((version) => {
          const isCurrent = version.slug === currentVersion.slug

          if (version.status === 'planned') {
            return (
              <div
                key={version.slug}
                className="text-muted-foreground flex min-h-12 items-center justify-between gap-3 rounded px-2.5 py-2 text-sm"
                aria-disabled="true"
              >
                <span>
                  <span className="text-foreground/60 block font-medium">
                    {version.game}
                  </span>
                  <span className="mt-0.5 block text-xs">
                    {version.version}
                  </span>
                </span>
                <span className="shrink-0 text-[11px] tracking-wide">
                  建设中
                </span>
              </div>
            )
          }

          return (
            <Link
              key={version.slug}
              href={replaceVersionInPathname(pathname, version.slug)}
              className="hover:bg-muted focus-visible:ring-ring flex min-h-12 items-center justify-between gap-3 rounded px-2.5 py-2 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <span>
                <span className="block font-medium">{version.game}</span>
                <span className="text-muted-foreground mt-0.5 block text-xs">
                  {version.version}
                </span>
              </span>
              {isCurrent && (
                <Check className="size-4 text-[var(--mm-signal)]" />
              )}
            </Link>
          )
        })}
      </div>
    </details>
  )
}
