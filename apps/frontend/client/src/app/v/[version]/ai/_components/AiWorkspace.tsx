'use client'

import { type FormEvent, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowUpRight, BookOpenText, Send } from 'lucide-react'

import { askQuestion, getModelStatus } from '@/api/ai'
import type { GameVersion } from '@/config/game-versions'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { formatReaderText } from '@/lib/reader-text'
import { Button } from '@/components/ui/button'

const suggestions = [
  '辅助涡轮装在二号槽时，3星载重和70%加成怎样计算？',
  '戴达罗斯的掉落槽概率能直接相加吗？',
  '药品知识学会后，换副职业还有效吗？',
  '主线取得越野车后，去海湾大桥前要做什么？',
] as const

export function AiWorkspace({ version }: { version: GameVersion }) {
  const [question, setQuestion] = useState('')
  const controller = useRef<AbortController | null>(null)
  const user = useCurrentUser()
  const model = useQuery({
    queryKey: ['model-status'],
    queryFn: getModelStatus,
    enabled: Boolean(user.data),
  })
  const answer = useMutation({
    mutationFn: async (text: string) => {
      controller.current = new AbortController()
      return askQuestion(version.slug, text, controller.current.signal)
    },
  })
  useEffect(() => () => controller.current?.abort(), [])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (question.trim() && user.data && !answer.isPending)
      answer.mutate(question.trim())
  }

  return (
    <div className="grid min-w-0 gap-8 xl:grid-cols-[minmax(0,1fr)_19rem]">
      <section className="min-w-0">
        <div className="border-border flex flex-wrap items-center justify-between gap-3 border-b pb-4 text-sm">
          <span>
            {version.game} · {version.version}
          </span>
          <span className="text-muted-foreground text-xs">
            {model.data?.model
              ? `当前模型：${model.data.model}`
              : '基于当前版本已收录资料'}
          </span>
        </div>
        {user.isPending && (
          <p className="text-muted-foreground py-6 text-sm">
            正在确认登录状态…
          </p>
        )}
        {user.isError && (
          <p role="alert" className="text-destructive py-6 text-sm">
            {user.error.message}{' '}
            <button
              type="button"
              onClick={() => user.refetch()}
              className="underline"
            >
              重新连接
            </button>
          </p>
        )}
        {user.isSuccess && !user.data && (
          <div className="bg-muted my-5 px-4 py-4 text-sm leading-6">
            <p>登录后可以提问，百科资料仍可直接浏览。</p>
            <Link
              className="mt-2 inline-flex min-h-10 items-center font-medium text-[var(--mm-navy)] underline"
              href={`/login?next=${encodeURIComponent(`/v/${version.slug}/ai`)}`}
            >
              登录或注册
            </Link>
          </div>
        )}
        {model.isError && (
          <p role="alert" className="text-destructive my-4 text-sm">
            {model.error.message}
          </p>
        )}
        {model.data && !model.data.configured && (
          <p role="alert" className="text-destructive my-4 text-sm">
            问答服务尚未配置模型，请联系站点维护者。
          </p>
        )}

        <div className="space-y-2 py-6">
          <p className="text-muted-foreground mb-3 text-xs">
            从具体名称和条件开始，也可以比较不同条目
          </p>
          {suggestions.map((text) => (
            <button
              key={text}
              type="button"
              onClick={() => setQuestion(text)}
              disabled={answer.isPending}
              className="border-border hover:bg-muted focus-visible:ring-ring block min-h-11 w-full border-b px-2 py-3 text-left text-sm focus-visible:ring-2"
            >
              {text}
            </button>
          ))}
        </div>

        <form onSubmit={submit}>
          <label htmlFor="question" className="text-sm font-medium">
            你的问题
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={1000}
            rows={4}
            disabled={answer.isPending}
            placeholder="输入装备、战车、职业、任务或攻略地点，以及想了解的具体条件…"
            className="border-input bg-card focus-visible:ring-ring mt-2 block w-full resize-y rounded-md border px-3 py-3 text-sm leading-6 focus-visible:ring-2 focus-visible:outline-none"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span className="text-muted-foreground text-xs">
              {question.length} / 1000 · 每次问题独立检索
            </span>
            <div className="flex gap-2">
              {answer.isPending && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => controller.current?.abort()}
                >
                  取消
                </Button>
              )}
              <Button
                type="submit"
                disabled={
                  !user.data ||
                  !model.data?.configured ||
                  !question.trim() ||
                  answer.isPending
                }
              >
                <Send />
                {answer.isPending ? '正在检索和回答…' : '发送问题'}
              </Button>
            </div>
          </div>
        </form>
        {answer.isError && (
          <p role="alert" className="text-destructive mt-5 text-sm">
            {answer.error.name === 'AbortError'
              ? '已取消本次请求。'
              : answer.error.message}
          </p>
        )}
        {user.data && answer.isSuccess && (
          <section
            aria-live="polite"
            className="border-border mt-8 border-t pt-6"
          >
            <h2 className="text-lg font-semibold text-[var(--mm-navy)]">
              {answer.data.status === 'insufficient_evidence'
                ? '暂缺足够证据'
                : '回答'}
            </h2>
            <p className="mt-2 text-sm font-medium">{answer.variables}</p>
            <p className="mt-4 text-sm leading-8 break-words whitespace-pre-wrap">
              {answer.data.answer}
            </p>
          </section>
        )}
      </section>
      <aside className="border-border min-w-0 border-t pt-5 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-6">
        <BookOpenText className="size-5 text-[var(--mm-signal)]" />
        <h2 className="mt-3 font-semibold text-[var(--mm-navy)]">回答引用</h2>
        {user.data && answer.isSuccess && answer.data.sources.length > 0 ? (
          <ol className="mt-4 space-y-5">
            {answer.data.sources.map((source) => (
              <li key={source.chunkId}>
                <Link
                  href={source.href}
                  className="inline-flex min-h-10 items-center gap-1 text-sm font-medium text-[var(--mm-navy)] underline-offset-4 hover:underline"
                >
                  [{source.number}] {source.title}
                  <ArrowUpRight className="size-3.5 shrink-0" />
                </Link>
                <p className="text-muted-foreground mt-1 line-clamp-5 text-xs leading-6 break-words">
                  {formatReaderText(source.excerpt)}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-muted-foreground mt-3 text-sm leading-6">
            回答后，这里会列出实际引用的资料。没有依据的问题会明确提示未收录。
          </p>
        )}
      </aside>
    </div>
  )
}
