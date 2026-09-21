import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { guides } from '@/data/fixtures/guides'
import { GuideArticle } from '@/components/guides/GuideArticle'

export const metadata: Metadata = {
  title: '攻略详情',
}

interface GuidePageProps {
  params: Promise<{ version: string; slug: string }>
}

export default async function GuidePage({ params }: GuidePageProps) {
  const { version: versionSlug, slug } = await params
  const version = getGameVersion(versionSlug)
  const guide = guides.find((item) => item.slug === slug)

  if (!version || !isAvailableGameVersion(version) || !guide) {
    notFound()
  }

  return <GuideArticle guide={guide} version={version} />
}
