import Image from 'next/image'

import { ExternalLink } from 'lucide-react'

import type { GuideDiagram, GuideFact } from '@/data/guides'

const rawValueLabels: Readonly<Record<string, string>> = {
  soldiers_raw: '士兵数量',
  tanks_raw: '战车数量',
  repair_kit_raw: '修理工具数量',
  museum_password_raw: '博物馆密码',
  dialogue_raw: '来源对话选项',
  room_price_raw: '房间费用',
  battle_count_raw: '战斗次数',
  operations_raw: '操作次数',
  total_neuro_units_raw: '神经元装置总数',
  placements_raw: '来源等级配置',
  left_password_raw: '左侧门禁密码',
  right_password_raw: '右侧门禁密码',
  full_drink_uses_raw: '满回复饮料使用次数',
  stages_raw: '战斗阶段数',
  battle_structure_raw: '来源战斗构成',
}

interface GuideFactContentProps {
  fact: GuideFact
}

/** 展示操作与来源原值，并将短证据保留在可展开的出处说明中。 */
export function GuideFactContent({ fact }: GuideFactContentProps) {
  const rawValues = Object.entries(fact.rawValues).map(([key, value]) => {
    const label = rawValueLabels[key]
    if (!label) throw new Error('攻略来源原值缺少中文字段说明，请更新攻略资料')
    return { key, label, value }
  })

  return (
    <div className="min-w-0">
      <p className="text-foreground/90 leading-8 text-pretty">{fact.textZh}</p>
      {rawValues.length > 0 ? (
        <dl className="border-border mt-3 grid gap-x-5 gap-y-2 border-l-2 pl-4 text-sm sm:grid-cols-[auto_1fr]">
          {rawValues.map(({ key, label, value }) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="min-w-0 font-medium break-words">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <details className="text-muted-foreground mt-3 text-sm">
        <summary className="focus-visible:ring-ring w-fit cursor-pointer py-1 text-xs hover:text-[var(--mm-signal)] focus-visible:ring-2 focus-visible:outline-none">
          查看原文证据与出处
        </summary>
        <div className="border-border mt-2 space-y-3 border-l pl-4 leading-6">
          <p className="text-xs">日文来源短证据，供核对操作条件：</p>
          {fact.evidence.map((evidence) => (
            <blockquote key={evidence} lang="ja" className="break-words">
              {evidence}
            </blockquote>
          ))}
          <a
            href={fact.sourceRef.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="focus-visible:ring-ring inline-flex min-h-9 items-center gap-1.5 text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
          >
            查看对应来源章节
            <ExternalLink aria-hidden="true" className="size-3.5" />
          </a>
          <p className="text-xs">
            来源采集于{' '}
            {new Date(fact.sourceRef.retrievedAt).toLocaleDateString('zh-CN', {
              timeZone: 'UTC',
            })}
            ，尚未逐项核对 0.99 实机。
          </p>
        </div>
      </details>
    </div>
  )
}

interface GuideDiagramFigureProps {
  diagram: GuideDiagram
}

/** 展示本地原创事件流程示意，保留作者与非地图声明。 */
export function GuideDiagramFigure({ diagram }: GuideDiagramFigureProps) {
  return (
    <figure className="border-border overflow-hidden rounded-lg border bg-[#f4f7fa]">
      <Image
        src={diagram.publicPath}
        alt={diagram.altZh}
        width={diagram.width}
        height={diagram.height}
        sizes="(max-width: 768px) 100vw, 840px"
        unoptimized
        className="mx-auto h-auto w-full max-w-[52.5rem]"
      />
      <figcaption className="border-border flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-xs leading-6 sm:px-5">
        <span>
          <span className="block font-medium text-[var(--mm-navy)]">
            {diagram.titleZh}
          </span>
          <span className="text-muted-foreground">
            {diagram.author} · {diagram.captionZh}
          </span>
        </span>
        <a
          href={diagram.publicPath}
          target="_blank"
          rel="noreferrer"
          className="focus-visible:ring-ring inline-flex min-h-9 items-center gap-1.5 text-[var(--mm-signal)] hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          打开大图
          <ExternalLink aria-hidden="true" className="size-3.5" />
        </a>
      </figcaption>
    </figure>
  )
}
