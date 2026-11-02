import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { Suspense } from 'react'

import { ArrowLeft, ChevronRight } from 'lucide-react'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { equipmentTypeById } from '@/config/equipment-types'
import { formatReaderText } from '@/lib/reader-text'
import {
  getEquipmentEntries,
  getEquipmentEntry,
} from '@/data/equipment/catalog'
import { Badge } from '@/components/ui/badge'
import { EquipmentSourceReferences } from '@/components/equipment/EquipmentSourceReferences'
import { AttributeTable } from '@/components/wiki/AttributeTable'

import { EquipmentReturnLink } from './_components/EquipmentReturnLink'
import { EquipmentModifications } from './_components/EquipmentModifications'
import { EngineUpgrades } from './_components/EngineUpgrades'
import {
  buildEquipmentDetailAttributes,
  equipmentIssueLabels,
  equipmentNameSourceLabels,
} from './_lib/equipment-detail'

interface EquipmentDetailPageProps {
  params: Promise<{ version: string; id: string }>
}

export const dynamicParams = false

export function generateStaticParams() {
  return getEquipmentEntries().map((entry) => ({
    version: 'mm2r-099',
    id: entry.id,
  }))
}

export async function generateMetadata({
  params,
}: EquipmentDetailPageProps): Promise<Metadata> {
  const { version: versionSlug, id } = await params
  const version = getGameVersion(versionSlug)
  const entry = getEquipmentEntry(id)
  const typeConfig = entry && equipmentTypeById.get(entry.type)

  if (
    version === undefined ||
    !isAvailableGameVersion(version) ||
    entry === undefined ||
    typeConfig === undefined
  ) {
    notFound()
  }

  return {
    title: `${entry.name}｜装备百科`,
    alternates: {
      canonical: `https://mm.yangyunqiao.top/v/${version.slug}/wiki/equipment/${entry.id}`,
    },
  }
}

export default async function EquipmentDetailPage({
  params,
}: EquipmentDetailPageProps) {
  const { version: versionSlug, id } = await params
  const version = getGameVersion(versionSlug)
  const entry = getEquipmentEntry(id)
  const typeConfig = entry && equipmentTypeById.get(entry.type)

  if (
    version === undefined ||
    !isAvailableGameVersion(version) ||
    entry === undefined ||
    typeConfig === undefined
  ) {
    notFound()
  }

  const defaultEquipmentHref = `/v/${version.slug}/wiki/equipment?type=${entry.type}`
  const attributes = buildEquipmentDetailAttributes(entry)

  return (
    <article className="mx-auto max-w-6xl pb-12">
      <nav
        aria-label="面包屑"
        className="text-foreground flex min-w-0 flex-wrap items-center gap-1.5 text-sm"
      >
        <Link
          href={`/v/${version.slug}`}
          className="hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center focus-visible:ring-2 focus-visible:outline-none"
        >
          情报总览
        </Link>
        <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />
        <Suspense
          fallback={
            <Link
              href={defaultEquipmentHref}
              className="hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center focus-visible:ring-2 focus-visible:outline-none"
            >
              装备百科
            </Link>
          }
        >
          <EquipmentReturnLink
            version={version.slug}
            variant="breadcrumb"
            equipmentType={entry.type}
          />
        </Suspense>
        <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="text-foreground min-w-0 break-words">
          {entry.name}
        </span>
      </nav>

      <header className="border-border mt-7 border-b pb-9">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="rounded text-[var(--mm-navy)]">
            {typeConfig.label}
          </Badge>
        </div>

        <h1 className="mt-5 text-3xl font-semibold tracking-[-0.035em] break-words text-[var(--mm-navy)] sm:text-4xl lg:text-[2.75rem]">
          {entry.name}
        </h1>
        <p className="text-foreground mt-2 text-sm">
          名称来源：{equipmentNameSourceLabels[entry.nameSource]}
        </p>
      </header>

      <div className="mt-9 grid min-w-0 gap-12 xl:grid-cols-[minmax(0,1fr)_19rem] xl:items-start">
        <div className="min-w-0 space-y-10">
          <AttributeTable attributes={attributes} />
          <EngineUpgrades entry={entry} version={version.slug} />
          <EquipmentModifications entry={entry} />
          <EquipmentSourceReferences
            sources={entry.source_refs}
            calculationSource={
              typeof entry.attributes.trait_calculation_source_raw === 'string'
                ? entry.attributes.trait_calculation_source_raw
                : undefined
            }
          />
        </div>

        <aside className="min-w-0 space-y-8 xl:sticky xl:top-24">
          <section aria-labelledby="equipment-names-heading">
            <h2
              id="equipment-names-heading"
              className="text-lg font-semibold tracking-tight text-[var(--mm-navy)]"
            >
              名称资料
            </h2>
            <dl className="border-border mt-4 border-t">
              {entry.names.zh_099 !== null && (
                <div className="border-border min-w-0 border-b py-3">
                  <dt className="text-foreground text-xs font-medium">
                    {equipmentNameSourceLabels.zh_099}
                  </dt>
                  <dd className="text-foreground mt-1 break-words">
                    {entry.names.zh_099}
                  </dd>
                </div>
              )}
              {entry.names.zh_09 !== null && (
                <div className="border-border min-w-0 border-b py-3">
                  <dt className="text-foreground text-xs font-medium">
                    {equipmentNameSourceLabels.zh_09}
                  </dt>
                  <dd className="text-foreground mt-1 break-words">
                    {entry.names.zh_09}
                  </dd>
                </div>
              )}
              {entry.names.ja !== null && (
                <div className="border-border min-w-0 border-b py-3">
                  <dt className="text-foreground text-xs font-medium">
                    {equipmentNameSourceLabels.ja}
                  </dt>
                  <dd className="text-foreground mt-1 break-words">
                    {entry.names.ja}
                  </dd>
                </div>
              )}
              {entry.names.zh_reference && (
                <div className="border-border min-w-0 border-b py-3">
                  <dt className="text-foreground text-xs font-medium">
                    中文参考译名
                  </dt>
                  <dd className="text-foreground mt-1 break-words">
                    {entry.names.zh_reference}
                  </dd>
                </div>
              )}
              {entry.names.aliases.length > 0 && (
                <div className="border-border min-w-0 border-b py-3">
                  <dt className="text-foreground text-xs font-medium">别名</dt>
                  <dd className="text-foreground mt-1 break-words">
                    {entry.names.aliases.join(' / ')}
                  </dd>
                </div>
              )}
            </dl>
          </section>

          {entry.issues.length > 0 && (
            <section aria-labelledby="equipment-issues-heading">
              <h2
                id="equipment-issues-heading"
                className="text-lg font-semibold tracking-tight text-[var(--mm-navy)]"
              >
                数据说明
              </h2>
              <ul className="border-border mt-4 border-t">
                {entry.issues.map((issue, index) => (
                  <li
                    key={`${issue}:${index}`}
                    className="border-border text-foreground min-w-0 border-b py-3 text-sm break-words"
                  >
                    {formatReaderText(equipmentIssueLabels[issue] ?? issue)}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>

      <Suspense
        fallback={
          <Link
            href={defaultEquipmentHref}
            className="focus-visible:ring-ring mt-10 inline-flex min-h-10 items-center gap-2 text-sm font-medium text-[var(--mm-navy)] underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            返回装备列表
          </Link>
        }
      >
        <EquipmentReturnLink
          version={version.slug}
          variant="footer"
          equipmentType={entry.type}
        />
      </Suspense>
    </article>
  )
}
