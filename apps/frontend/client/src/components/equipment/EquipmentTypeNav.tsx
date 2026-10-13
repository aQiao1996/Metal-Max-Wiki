import Link from 'next/link'

import { cn } from 'cn'

import type { GameVersionSlug } from '@/config/game-versions'
import { equipmentTypes } from '@/config/equipment-types'
import type { EquipmentQuery, EquipmentTypeId } from '@/types/equipment'

interface EquipmentTypeNavProps {
  counts: ReadonlyMap<EquipmentTypeId, number>
  query: EquipmentQuery
  version: GameVersionSlug
}

export function EquipmentTypeNav({
  counts,
  query,
  version,
}: EquipmentTypeNavProps) {
  return (
    <nav
      aria-label="装备类型"
      className="border-border max-w-full overflow-x-auto overscroll-x-contain border-b"
    >
      <div className="flex min-w-max gap-6 px-1">
        {equipmentTypes.map((type) => {
          const isCurrent = type.id === query.type
          const search = new URLSearchParams({ type: type.id })

          if (query.q !== '') {
            search.set('q', query.q)
          }

          return (
            <Link
              key={type.id}
              href={`/v/${version}/wiki/equipment?${search.toString()}`}
              aria-current={isCurrent ? 'page' : undefined}
              className={cn(
                'focus-visible:ring-ring -mb-px inline-flex min-h-11 items-center gap-2 border-b-2 px-0.5 text-sm whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:outline-none',
                isCurrent
                  ? 'border-[var(--mm-signal)] font-semibold text-[var(--mm-navy)]'
                  : 'text-foreground border-transparent hover:border-[var(--mm-navy)] hover:text-[var(--mm-navy)]',
              )}
            >
              <span>{type.label}</span>
              <span
                className={cn(
                  'rounded-sm px-1.5 py-0.5 font-mono text-[0.6875rem]',
                  isCurrent
                    ? 'bg-accent text-accent-foreground'
                    : 'bg-muted text-foreground',
                )}
              >
                {counts.get(type.id) ?? 0}
              </span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
