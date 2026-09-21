import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { guides } from '@/data/fixtures/guides'
import { GuideList } from '@/components/guides/GuideList'

export const metadata: Metadata = {
  title: '攻略整理',
}

interface GuidesPageProps {
  params: Promise<{ version: string }>
}

export default async function GuidesPage({ params }: GuidesPageProps) {
  const { version: versionSlug } = await params
  const version = getGameVersion(versionSlug)

  if (!version || !isAvailableGameVersion(version)) {
    notFound()
  }

  return (
    <div className="mx-auto max-w-5xl pb-12">
      <header className="border-border border-b pb-8">
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--mm-signal)] uppercase">
          Field guides
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          攻略与实机记录
        </h1>
        <p className="text-muted-foreground mt-3 max-w-2xl leading-7 text-pretty">
          围绕 {version.version}整理的改造、装备和数据核对方法。
        </p>
      </header>

      <section className="py-7">
        <GuideList guides={guides} version={version.slug} />
      </section>
    </div>
  )
}
