import Link from 'next/link'

import type { GameVersionSlug } from '@/config/game-versions'
import { getEquipmentEntries } from '@/data/equipment/catalog'
import type { EquipmentEntry } from '@/types/equipment'

/** 按来源中的下一型号显示强化路径，不根据名称推测升级关系。 */
export function EngineUpgrades({
  entry,
  version,
}: {
  entry: EquipmentEntry
  version: GameVersionSlug
}) {
  if (entry.type !== 'engine') return null
  const engines = getEquipmentEntries().filter((item) => item.type === 'engine')
  const previous = engines.filter(
    (item) => item.attributes.upgrade_to_ja_raw === entry.names.ja,
  )
  const path = [entry]
  const visited = new Set([entry.id])
  let current = entry
  while (current.attributes.upgrade_to_ja_raw !== undefined) {
    const target = engines.find(
      (item) => item.names.ja === current.attributes.upgrade_to_ja_raw,
    )
    if (!target || visited.has(target.id))
      throw new Error(`引擎强化路径无效：${current.id}`)
    visited.add(target.id)
    path.push(target)
    current = target
  }
  if (previous.length === 0 && path.length === 1) return null

  return (
    <section aria-labelledby="engine-upgrades-heading">
      <h2
        id="engine-upgrades-heading"
        className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        马力强化路径
      </h2>
      <p className="text-muted-foreground mt-3 text-sm leading-6">
        费用为本次强化到下一型号的价格，不含购买费与此前强化费。载重仍需按星级和特性条件比较。
      </p>
      {previous.length > 0 && (
        <p className="text-foreground mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <span>前一级：</span>
          {previous.map((item) => (
            <Link
              key={item.id}
              href={`/v/${version}/wiki/equipment/${item.id}`}
              className="focus-visible:ring-ring inline-flex min-h-10 items-center underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
            >
              {item.name}
            </Link>
          ))}
        </p>
      )}
      <ol className="border-border mt-4 border-t">
        {path.map((item, index) => (
          <li
            key={item.id}
            className="border-border flex min-w-0 flex-wrap items-center justify-between gap-3 border-b py-3 text-sm"
          >
            <Link
              href={`/v/${version}/wiki/equipment/${item.id}`}
              aria-current={item.id === entry.id ? 'page' : undefined}
              className="focus-visible:ring-ring inline-flex min-h-10 min-w-0 items-center gap-3 font-medium text-[var(--mm-navy)] underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
            >
              <span className="font-mono text-xs">
                {String(index + 1).padStart(2, '0')}
              </span>
              <span className="break-words">
                {item.name}
                {item.id === entry.id ? '（当前型号）' : ''}
              </span>
            </Link>
            <span className="text-muted-foreground">
              {item.attributes.upgrade_cost_raw !== undefined
                ? `→ 下一阶 ${item.attributes.upgrade_cost_raw} G`
                : '强化终点'}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
