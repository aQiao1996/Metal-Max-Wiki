import Link from 'next/link'

import { ArrowLeft } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import type { GuideDetail } from '@/types/wiki'

import { SourceReferences } from '../wiki/SourceReferences'

interface GuideArticleProps {
  guide: GuideDetail
  version: GameVersion
}

export function GuideArticle({ guide, version }: GuideArticleProps) {
  return (
    <article className="mx-auto max-w-6xl pb-12">
      <Link
        href={buildVersionPath(version.slug, '/guides')}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center gap-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
      >
        <ArrowLeft className="size-4" />
        攻略列表
      </Link>

      <header className="border-border mt-6 border-b pb-8">
        <p className="text-xs font-medium tracking-[0.14em] text-[var(--mm-signal)] uppercase">
          Field guide · {version.shortLabel}
        </p>
        <h1 className="mt-4 max-w-4xl text-3xl font-semibold tracking-[-0.035em] text-[var(--mm-navy)] sm:text-4xl lg:text-[2.75rem]">
          {guide.title}
        </h1>
        <p className="text-muted-foreground mt-4 max-w-3xl text-lg leading-8 text-pretty">
          {guide.summary}
        </p>
      </header>

      <div className="mt-9 grid gap-12 xl:grid-cols-[minmax(0,46rem)_15rem] xl:justify-between">
        <div className="min-w-0 space-y-11">
          {guide.sections.map((section) => (
            <section key={section.id} id={section.id} className="scroll-mt-24">
              <h2 className="text-2xl font-semibold tracking-tight text-[var(--mm-navy)]">
                {section.title}
              </h2>
              <div className="text-foreground/84 mt-4 space-y-4 text-base leading-8 text-pretty">
                {section.paragraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
              {section.table && (
                <div className="border-border bg-card mt-6 overflow-x-auto border">
                  <table className="w-full min-w-[32rem] border-collapse text-left text-sm">
                    <thead className="bg-muted text-[var(--mm-navy)]">
                      <tr>
                        {section.table.headers.map((header) => (
                          <th
                            key={header}
                            className="border-border border-b px-4 py-3 font-semibold"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {section.table.rows.map((row) => (
                        <tr
                          key={row.join(':')}
                          className="border-border border-b last:border-b-0"
                        >
                          {row.map((cell) => (
                            <td
                              key={cell}
                              className="px-4 py-3 align-top leading-6"
                            >
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ))}

          <SourceReferences sources={guide.sources} />
        </div>

        <aside className="hidden xl:block">
          <nav
            className="border-border sticky top-24 border-l pl-5"
            aria-label="本页目录"
          >
            <p className="text-muted-foreground text-xs font-semibold tracking-[0.12em] uppercase">
              本页目录
            </p>
            <ol className="mt-4 space-y-3">
              {guide.sections.map((section, index) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    className="text-muted-foreground hover:text-foreground focus-visible:ring-ring grid grid-cols-[1.5rem_1fr] text-sm leading-5 focus-visible:ring-2 focus-visible:outline-none"
                  >
                    <span className="font-mono text-[11px] text-[var(--mm-signal)]">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    {section.title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </aside>
      </div>
    </article>
  )
}
