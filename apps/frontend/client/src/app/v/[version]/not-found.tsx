import Link from 'next/link'

import { ArrowLeft, Search } from 'lucide-react'

import { defaultGameVersion } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'

export default function VersionNotFound() {
  return (
    <section className="mx-auto max-w-xl py-16 sm:py-24">
      <p className="font-mono text-sm text-[var(--mm-signal)]">
        404 / NOT FOUND
      </p>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight text-[var(--mm-navy)]">
        没有找到这份资料
      </h1>
      <p className="text-muted-foreground mt-3 leading-7 text-pretty">
        条目可能还未录入，也可能属于其他版本。可以返回当前已开放的资料库或使用搜索。
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href={buildVersionPath(defaultGameVersion)}
          className="focus-visible:ring-ring inline-flex min-h-11 items-center gap-2 rounded-md bg-[var(--mm-navy)] px-4 text-sm font-medium text-white hover:bg-[var(--mm-navy-deep)] focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          <ArrowLeft className="size-4" />
          返回情报总览
        </Link>
        <Link
          href={buildVersionPath(defaultGameVersion, '/search')}
          className="border-border bg-card hover:bg-muted focus-visible:ring-ring inline-flex min-h-11 items-center gap-2 rounded-md border px-4 text-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
        >
          <Search className="size-4" />
          搜索资料
        </Link>
      </div>
    </section>
  )
}
