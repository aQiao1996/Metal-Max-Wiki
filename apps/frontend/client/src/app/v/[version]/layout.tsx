import type { ReactNode } from 'react'
import { notFound } from 'next/navigation'

import { getGameVersion } from '@/config/game-versions'
import { MobileNavigation } from '@/components/layout/MobileNavigation'
import { SiteHeader } from '@/components/layout/SiteHeader'
import { SiteSidebar } from '@/components/layout/SiteSidebar'

interface VersionLayoutProps {
  children: ReactNode
  params: Promise<{ version: string }>
}

export default async function VersionLayout({
  children,
  params,
}: VersionLayoutProps) {
  const { version: versionSlug } = await params
  const version = getGameVersion(versionSlug)

  if (!version) {
    notFound()
  }

  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="fixed top-3 left-3 z-[100] -translate-y-20 rounded-md bg-[var(--mm-signal)] px-4 py-2 text-sm font-medium text-white transition-transform focus:translate-y-0"
      >
        跳到主要内容
      </a>
      <SiteSidebar version={version} />
      <MobileNavigation version={version} />
      <div className="min-h-screen md:pl-56">
        <SiteHeader version={version} />
        <main
          id="main-content"
          className="px-4 py-7 sm:px-6 md:px-7 lg:px-10 lg:py-10"
        >
          <div className="page-container">{children}</div>
        </main>
      </div>
    </div>
  )
}
