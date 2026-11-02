import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { getGuide } from '@/data/guides'
import { ApiError } from '@/lib/request'
import { GuideArticle } from '@/components/guides/GuideArticle'

interface GuidePageProps {
  params: Promise<{ version: string; slug: string }>
}

async function readGuide({ params }: GuidePageProps) {
  const { version: versionSlug, slug } = await params
  const version = getGameVersion(versionSlug)
  if (!version || !isAvailableGameVersion(version)) notFound()
  try {
    return { version, guide: await getGuide(version.slug, slug) }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }
}

export async function generateMetadata(
  props: GuidePageProps,
): Promise<Metadata> {
  const { guide } = await readGuide(props)
  return { title: guide.title, description: guide.summary }
}

export default async function GuidePage(props: GuidePageProps) {
  const { version, guide } = await readGuide(props)
  return <GuideArticle guide={guide} version={version} />
}
