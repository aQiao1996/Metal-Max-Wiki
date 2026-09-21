import { ExternalLink } from 'lucide-react'

import type { SourceReference } from '@/types/wiki'

interface SourceReferencesProps {
  sources: readonly SourceReference[]
}

export function SourceReferences({ sources }: SourceReferencesProps) {
  return (
    <section aria-labelledby="sources-heading">
      <h2
        id="sources-heading"
        className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        来源与校对
      </h2>
      {sources.length > 0 ? (
        <ol className="border-border mt-5 border-t">
          {sources.map((source, index) => (
            <li
              key={`${source.title}:${index}`}
              className="border-border grid gap-2 border-b py-4 sm:grid-cols-[2rem_1fr_auto] sm:gap-4"
            >
              <span className="font-mono text-xs text-[var(--mm-signal)]">
                {String(index + 1).padStart(2, '0')}
              </span>
              <span>
                <span className="block text-sm font-medium break-words">
                  {source.title}
                </span>
                <span className="text-muted-foreground mt-1 block text-sm leading-5">
                  {source.note}
                </span>
              </span>
              {source.href ? (
                <a
                  href={source.href}
                  target="_blank"
                  rel="noreferrer"
                  className="focus-visible:ring-ring inline-flex min-h-9 items-center gap-1.5 text-xs text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
                >
                  查看来源
                  <ExternalLink className="size-3.5" />
                </a>
              ) : (
                <span className="text-muted-foreground text-xs">
                  {source.status === 'verified' ? '已核对' : '待补充'}
                </span>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="border-border text-muted-foreground mt-4 border-y py-5 text-sm">
          来源记录尚未补充，本页不会将未核对内容标记为已验证。
        </p>
      )}
    </section>
  )
}
