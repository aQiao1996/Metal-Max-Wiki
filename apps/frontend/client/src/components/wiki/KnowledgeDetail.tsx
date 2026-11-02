import Link from 'next/link'

import { ArrowLeft, ChevronRight } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { toKnowledgeSources, type KnowledgeEntry } from '@/data/knowledge/entry'
import { cn } from '@/lib/utils'
import { buildVersionPath } from '@/lib/version-routes'
import type { WikiCategory } from '@/types/wiki'
import { EquipmentVerificationBadge } from '@/components/equipment/EquipmentVerificationBadge'
import { AttributeTable } from '@/components/wiki/AttributeTable'
import { ReferenceDataTable } from '@/components/wiki/ReferenceDataTable'
import { SourceReferences } from '@/components/wiki/SourceReferences'
import { VehicleConfigurations } from '@/components/wiki/VehicleConfigurations'

interface KnowledgeDetailProps {
  entry: KnowledgeEntry
  category: WikiCategory
  version: GameVersion
  returnHref?: string
}

function KnowledgeSection({
  section,
  folded = false,
  collapseTables = false,
}: {
  section: KnowledgeEntry['sections'][number]
  folded?: boolean
  collapseTables?: boolean
}) {
  const content = (
    <>
      <div className="mt-4 space-y-3 text-sm leading-7 sm:text-base">
        {section.paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>
      {section.tables.length > 0 && (
        <div className="mt-5 min-w-0 space-y-5">
          {collapseTables ? (
            <details>
              <summary className="focus-visible:ring-ring min-h-10 cursor-pointer py-2 text-sm font-medium text-[var(--mm-navy)] focus-visible:ring-2 focus-visible:outline-none">
                原文与来源记录
              </summary>
              <div className="mt-3 min-w-0 space-y-4">
                {section.tables.map((table, index) => (
                  <ReferenceDataTable
                    key={`${section.id}:${index}`}
                    table={table}
                  />
                ))}
              </div>
            </details>
          ) : (
            section.tables.map((table, index) => (
              <ReferenceDataTable
                key={`${section.id}:${index}`}
                table={table}
              />
            ))
          )}
        </div>
      )}
    </>
  )
  const heading = (
    <h2
      className={cn(
        'text-xl font-semibold tracking-tight text-[var(--mm-navy)]',
        folded && 'inline',
      )}
    >
      {section.title}
    </h2>
  )
  return folded ? (
    <details
      id={section.id}
      className="border-border min-w-0 scroll-mt-24 border-t pt-4"
    >
      <summary className="focus-visible:ring-ring min-h-11 cursor-pointer py-2 focus-visible:ring-2 focus-visible:outline-none">
        {heading}
      </summary>
      {content}
    </details>
  ) : (
    <section id={section.id} className="min-w-0 scroll-mt-24">
      {heading}
      {content}
    </section>
  )
}

/** 展示有来源的百科正文和独立掉落槽。 */
export function KnowledgeDetail({
  entry,
  category,
  version,
  returnHref,
}: KnowledgeDetailProps) {
  const listHref =
    returnHref ?? buildVersionPath(version.slug, `/wiki/${entry.category}`)
  const leadingSections = entry.vehicle
    ? entry.sections.filter((section) => section.id === 'acquisition')
    : []
  const remainingSections = entry.vehicle
    ? entry.sections.filter((section) => section.id !== 'acquisition')
    : entry.sections
  return (
    <article className="mx-auto max-w-6xl min-w-0 pb-12">
      <nav
        aria-label="面包屑"
        className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-sm"
      >
        <Link
          href={buildVersionPath(version.slug)}
          className="focus-visible:ring-ring inline-flex min-h-10 items-center focus-visible:ring-2 focus-visible:outline-none"
        >
          情报总览
        </Link>
        <ChevronRight className="size-3.5" aria-hidden="true" />
        <Link
          href={listHref}
          className="focus-visible:ring-ring inline-flex min-h-10 items-center focus-visible:ring-2 focus-visible:outline-none"
        >
          {category.label}
        </Link>
        <ChevronRight className="size-3.5" aria-hidden="true" />
        <span className="text-foreground">{entry.name}</span>
      </nav>

      <header className="border-border mt-6 border-b pb-8">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="border-border rounded border px-2 py-1 text-[var(--mm-navy)]">
            {category.label}
          </span>
          <EquipmentVerificationBadge status={entry.verification_status} />
        </div>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          {entry.name}
        </h1>
        {entry.names.ja && (
          <p className="text-muted-foreground mt-2 text-sm">
            日文原名：{entry.names.ja}
          </p>
        )}
        {entry.names.aliases.length > 0 && (
          <p className="text-muted-foreground mt-2 text-sm">
            别名：{entry.names.aliases.join(' / ')}
          </p>
        )}
        <p className="text-muted-foreground mt-4 max-w-3xl leading-7">
          {entry.summary}
        </p>
        <p className="mt-5 max-w-3xl border-l-2 border-[var(--mm-signal)] bg-[#f5e8e2] px-4 py-3 text-sm leading-6 text-[#81432e]">
          日版资料与中文参考译名，尚未完成 0.99 实机核验。
        </p>
      </header>

      <div className="mt-8 grid min-w-0 gap-10 xl:grid-cols-[minmax(0,1fr)_15rem]">
        <div className="min-w-0 space-y-10">
          <AttributeTable attributes={entry.attributes} />
          {leadingSections.map((section) => (
            <KnowledgeSection
              key={section.id}
              section={section}
              collapseTables
            />
          ))}
          {entry.vehicle && (
            <VehicleConfigurations
              vehicle={entry.vehicle}
              vehicleId={entry.id}
            />
          )}
          {remainingSections.map((section) => (
            <KnowledgeSection
              key={section.id}
              section={section}
              folded={
                entry.vehicle !== undefined &&
                [
                  'initial-equipment',
                  'individual-modifications',
                  'traits',
                  'purchase-options',
                ].includes(section.id)
              }
            />
          ))}

          {entry.enemies.length > 0 && (
            <section
              id="drops"
              className="min-w-0 scroll-mt-24"
              aria-labelledby="drops-heading"
            >
              <h2
                id="drops-heading"
                className="text-xl font-semibold text-[var(--mm-navy)]"
              >
                掉落物品
              </h2>
              <p className="text-muted-foreground mt-3 text-xs leading-6">
                {entry.probability_note}
              </p>
              {entry.enemies.map((enemy) => (
                <div key={enemy.name_ja} className="mt-5 min-w-0">
                  {entry.enemies.length > 1 && (
                    <h3 className="mb-3 text-sm font-semibold text-[var(--mm-navy)]">
                      {enemy.name_ja} · 图鉴 {enemy.encyclopedia_number}
                    </h3>
                  )}
                  <ol className="border-border border-t">
                    {enemy.drops.map((drop) => (
                      <li
                        key={drop.slot}
                        className="border-border min-w-0 border-b py-5"
                      >
                        <div className="flex items-baseline justify-between gap-3">
                          <div className="min-w-0">
                            <span className="text-muted-foreground mr-2 font-mono text-xs">
                              {String(drop.slot).padStart(2, '0')}
                            </span>
                            {drop.equipment_id ? (
                              <Link
                                href={buildVersionPath(
                                  version.slug,
                                  `/wiki/equipment/${drop.equipment_id}`,
                                )}
                                className="focus-visible:ring-ring font-semibold text-[var(--mm-signal)] underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
                              >
                                {drop.name}
                              </Link>
                            ) : (
                              <span className="font-semibold text-[var(--mm-navy)]">
                                {drop.name}
                              </span>
                            )}
                          </div>
                          <span className="shrink-0 font-mono text-base font-semibold text-[var(--mm-navy)] tabular-nums">
                            {drop.rate_raw}
                          </span>
                        </div>
                        <p className="text-muted-foreground mt-2 text-xs break-words">
                          {drop.item_ja}
                        </p>
                        {drop.summary && (
                          <p className="mt-3 text-sm leading-6">
                            {drop.summary}
                          </p>
                        )}
                        {drop.attributes.length > 0 && (
                          <dl className="mt-3 grid gap-x-5 gap-y-2 text-sm sm:grid-cols-2">
                            {drop.attributes.map((attribute, index) => (
                              <div key={index} className="min-w-0">
                                <dt className="text-muted-foreground inline">
                                  {attribute.label}：
                                </dt>
                                <dd className="inline break-words">
                                  {attribute.value}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        )}
                        {drop.tables.length > 0 && (
                          <details className="mt-3 min-w-0">
                            <summary className="focus-visible:ring-ring min-h-10 cursor-pointer py-2 text-sm font-medium text-[var(--mm-navy)] focus-visible:ring-2 focus-visible:outline-none">
                              原表数值与星级条件
                            </summary>
                            <div className="mt-3 min-w-0 space-y-4">
                              {drop.tables.map((table, index) => (
                                <ReferenceDataTable key={index} table={table} />
                              ))}
                              <p className="text-muted-foreground text-xs leading-6">
                                数值按各自条件与星级分别列出，不能混用；列出某星级不代表掉落时可获得该星级。—
                                表示来源未注明，数值不含超改造。
                              </p>
                            </div>
                          </details>
                        )}
                        {drop.issues.length > 0 && (
                          <p className="text-muted-foreground mt-3 text-xs leading-6">
                            部分字段仍待核对，已保留来源记录。
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </section>
          )}
          <SourceReferences sources={toKnowledgeSources(entry)} />
        </div>
        <aside className="border-border border-t pt-5 xl:sticky xl:top-24 xl:self-start">
          <h2 className="text-sm font-semibold text-[var(--mm-navy)]">
            本页目录
          </h2>
          <nav aria-label="条目目录" className="mt-3 flex flex-col text-sm">
            {entry.vehicle && (
              <a
                href="#configurations"
                className="focus-visible:ring-ring inline-flex min-h-10 items-center py-1 text-[var(--mm-navy)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
              >
                {entry.vehicle.configurations.every(
                  (setup) => setup.kind === 'preset',
                )
                  ? '设计预设'
                  : '底盘配置'}
              </a>
            )}
            {entry.sections.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className="focus-visible:ring-ring inline-flex min-h-10 items-center py-1 text-[var(--mm-navy)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
              >
                {section.title}
              </a>
            ))}
            {entry.enemies.length > 0 && (
              <a
                href="#drops"
                className="focus-visible:ring-ring inline-flex min-h-10 items-center hover:underline focus-visible:ring-2 focus-visible:outline-none"
              >
                掉落物品
              </a>
            )}
            <a
              href="#sources-heading"
              className="focus-visible:ring-ring inline-flex min-h-10 items-center hover:underline focus-visible:ring-2 focus-visible:outline-none"
            >
              来源与校对
            </a>
          </nav>
          <p className="text-muted-foreground mt-5 text-xs leading-6">
            {version.game} · {version.version}
          </p>
        </aside>
      </div>
      <Link
        href={listHref}
        className="focus-visible:ring-ring mt-8 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-[var(--mm-navy)] focus-visible:ring-2 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        返回{category.label}列表
      </Link>
    </article>
  )
}
