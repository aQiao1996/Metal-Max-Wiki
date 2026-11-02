'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'

import { ArrowRight, Search } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { searchLibrary, suggestedSearches } from '@/api/search'
import { buildVersionPath } from '@/lib/version-routes'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { EquipmentVerificationBadge } from '@/components/equipment/EquipmentVerificationBadge'

interface GlobalSearchDialogProps {
  version: GameVersion
  compact?: boolean
}

export function GlobalSearchDialog({
  version,
  compact = false,
}: GlobalSearchDialogProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const router = useRouter()
  useEffect(() => {
    const timer = setTimeout(() => setSearchTerm(query.trim()), 250)
    return () => clearTimeout(timer)
  }, [query])
  const results = useQuery({
    queryKey: ['library-search', version.slug, searchTerm],
    queryFn: ({ signal }) => searchLibrary(version.slug, searchTerm, signal),
    enabled: open && searchTerm.length > 0,
    staleTime: 30000,
  })
  const matchedResults = results.data?.list ?? []

  useEffect(() => {
    const mobileViewport = window.matchMedia('(width < 48rem)')
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        if (compact !== mobileViewport.matches) return
        event.preventDefault()
        setOpen(true)
      }
    }
    const closeWhenHidden = () => {
      if (compact !== mobileViewport.matches) setOpen(false)
    }

    window.addEventListener('keydown', handleShortcut)
    mobileViewport.addEventListener('change', closeWhenHidden)
    return () => {
      window.removeEventListener('keydown', handleShortcut)
      mobileViewport.removeEventListener('change', closeWhenHidden)
    }
  }, [compact])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {compact ? (
          <Button variant="ghost" size="icon" aria-label="搜索资料">
            <Search className="size-5" />
          </Button>
        ) : (
          <button className="border-border bg-card text-muted-foreground hover:text-foreground focus-visible:ring-ring flex h-10 w-full max-w-xl items-center gap-3 rounded-md border px-3.5 text-left text-sm transition-colors hover:border-[#b9c5c9] focus-visible:ring-2 focus-visible:outline-none">
            <Search className="size-4" />
            <span className="flex-1">搜索名称、地点或掉落物品</span>
            <kbd className="border-border bg-muted text-muted-foreground rounded border px-1.5 py-0.5 font-mono text-[11px]">
              ⌘K
            </kbd>
          </button>
        )}
      </DialogTrigger>

      <DialogContent className="top-[12vh] max-h-[76vh] max-w-2xl translate-y-0 gap-0 overflow-hidden p-0 sm:top-[14vh] sm:max-w-2xl">
        <DialogHeader className="border-border border-b px-5 py-4 pr-12">
          <DialogTitle>搜索资料库</DialogTitle>
          <DialogDescription>
            范围：{version.game} · {version.version}
          </DialogDescription>
        </DialogHeader>

        <div className="border-border border-b p-4">
          <label className="relative block">
            <span className="sr-only">输入搜索内容</span>
            <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === 'Enter' &&
                  !event.nativeEvent.isComposing &&
                  query.trim()
                ) {
                  router.push(
                    `${buildVersionPath(version.slug, '/search')}?q=${encodeURIComponent(query.trim())}`,
                  )
                  setOpen(false)
                }
              }}
              maxLength={100}
              placeholder="例如：宇宙炮、亚当蚁"
              className="h-11 pl-9"
            />
          </label>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-3">
          {!query && (
            <div className="mb-3 px-2 pt-1">
              <p className="text-muted-foreground mb-2 text-[11px] font-medium tracking-[0.12em] uppercase">
                可以从这里开始
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestedSearches.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setQuery(item)}
                    className="border-border bg-card hover:bg-muted focus-visible:ring-ring min-h-9 rounded-md border px-3 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="text-muted-foreground px-2 pt-2 pb-1 text-[11px] font-medium tracking-[0.12em] uppercase">
            {query ? '匹配结果' : '装备与赏金首资料'}
          </p>
          {searchTerm && (results.isFetching || searchTerm !== query.trim()) ? (
            <p role="status" className="text-muted-foreground p-4 text-sm">
              正在搜索…
            </p>
          ) : results.isError ? (
            <p role="alert" className="text-destructive p-4 text-sm">
              {results.error.message}
            </p>
          ) : matchedResults.length > 0 ? (
            <ul>
              {matchedResults.map((result) => (
                <li key={result.id}>
                  <Link
                    href={buildVersionPath(version.slug, result.href)}
                    onClick={() => setOpen(false)}
                    className="group hover:bg-muted focus-visible:ring-ring flex items-start gap-3 rounded-md px-2 py-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                  >
                    <span className="mt-0.5 min-w-15 text-xs font-medium text-[var(--mm-signal)]">
                      {result.categoryLabel}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="text-foreground flex flex-wrap items-center gap-2 font-medium">
                        <span>{result.name}</span>
                        {result.verificationStatus && (
                          <EquipmentVerificationBadge
                            status={result.verificationStatus}
                          />
                        )}
                      </span>
                      {result.nameSource === 'zh_reference' && (
                        <span className="text-muted-foreground mt-1 block text-xs">
                          中文参考译名
                        </span>
                      )}
                      <span className="text-muted-foreground mt-1 line-clamp-2 block text-sm leading-5">
                        {result.summary}
                      </span>
                    </span>
                    <ArrowRight className="text-muted-foreground mt-1 size-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : query.trim() ? (
            <div className="px-2 py-8 text-center">
              <p className="font-medium">没有匹配条目</p>
              <p className="text-muted-foreground mt-1 text-sm">
                尝试更换名称或简称。
              </p>
            </div>
          ) : null}
        </div>

        <div className="border-border bg-muted/55 text-muted-foreground border-t px-5 py-3 text-xs">
          回车查看全部结果 · Esc 关闭
        </div>
      </DialogContent>
    </Dialog>
  )
}
