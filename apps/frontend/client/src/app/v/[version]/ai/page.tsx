import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { getGameVersion, isAvailableGameVersion } from '@/config/game-versions'
import { AiWorkspace } from '@/components/ai/AiWorkspace'

export const metadata: Metadata = {
  title: 'AI 问答',
}

interface AiPageProps {
  params: Promise<{ version: string }>
}

export default async function AiPage({ params }: AiPageProps) {
  const { version: versionSlug } = await params
  const version = getGameVersion(versionSlug)

  if (!version || !isAvailableGameVersion(version)) {
    notFound()
  }

  return (
    <div className="mx-auto max-w-6xl pb-12">
      <header className="border-border border-b pb-7">
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--mm-signal)] uppercase">
          Ask the archive
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[var(--mm-navy)] sm:text-4xl">
          AI 问答
        </h1>
        <p className="text-muted-foreground mt-3 max-w-2xl leading-7 text-pretty">
          在当前版本已收录的装备资料中检索，回答附带引用，未收录的内容会明确说明。
        </p>
      </header>
      <div className="mt-7">
        <AiWorkspace version={version} />
      </div>
    </div>
  )
}
