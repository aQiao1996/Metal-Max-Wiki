'use client'

import { useState } from 'react'
import Link from 'next/link'

import { ArrowRight, BookOpenText, LockKeyhole, Send } from 'lucide-react'

import type { GameVersion } from '@/config/game-versions'
import { Button } from '@/components/ui/button'

interface AiWorkspacePreviewProps {
  version: GameVersion
}

const suggestedQuestions = [
  '红狼战车适合什么配装？',
  '宇宙炮的成长资料在哪里？',
  '查找已校对的赏金首掉落。',
] as const

export function AiWorkspacePreview({ version }: AiWorkspacePreviewProps) {
  const [question, setQuestion] = useState('')

  return (
    <div className="grid gap-7 xl:grid-cols-[minmax(0,1fr)_19rem]">
      <section className="border-border bg-card border">
        <div className="border-border border-b px-5 py-4 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-[var(--mm-signal)]">
                版本范围
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--mm-navy)]">
                {version.game} · {version.version}
              </p>
            </div>
            <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
              <LockKeyhole className="size-3.5" />
              需要登录
            </span>
          </div>
        </div>

        <div className="min-h-72 p-5 sm:p-6">
          <p className="text-sm font-medium text-[var(--mm-navy)]">
            可以这样问
          </p>
          <div className="mt-4 grid gap-2">
            {suggestedQuestions.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setQuestion(item)}
                className="border-border text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring min-h-11 border px-3 py-2.5 text-left text-sm transition-colors hover:border-[#b7c3c7] focus-visible:ring-2 focus-visible:outline-none"
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="border-border bg-muted/35 border-t p-4 sm:p-5">
          <label htmlFor="ai-question" className="sr-only">
            输入问题
          </label>
          <textarea
            id="ai-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="输入关于当前版本的问题……"
            rows={3}
            className="border-input bg-card placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/40 w-full resize-none rounded-md border px-3 py-2.5 text-sm leading-6 outline-none focus-visible:ring-2"
          />
          <div className="mt-3 flex flex-col-reverse justify-between gap-3 sm:flex-row sm:items-center">
            <p className="text-muted-foreground text-xs">
              登录后才能提交，回答将附带资料引用。
            </p>
            <Button disabled size="lg" className="sm:min-w-28">
              <Send />
              发送
            </Button>
          </div>
        </div>
      </section>

      <aside className="space-y-5">
        <div className="bg-card border-t-2 border-[var(--mm-navy)] p-5">
          <BookOpenText className="size-5 text-[var(--mm-signal)]" />
          <h2 className="mt-4 font-semibold text-[var(--mm-navy)]">引用位置</h2>
          <p className="text-muted-foreground mt-2 text-sm leading-6">
            登录后，这里会列出回答使用的百科条目、攻略段落和校对状态。
          </p>
        </div>
        <Link
          href="/login"
          className="group focus-visible:ring-ring flex min-h-11 items-center justify-between gap-3 rounded-md bg-[var(--mm-navy)] px-4 text-sm font-medium text-white hover:bg-[var(--mm-navy-deep)] focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          前往登录
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
        </Link>
      </aside>
    </div>
  )
}
