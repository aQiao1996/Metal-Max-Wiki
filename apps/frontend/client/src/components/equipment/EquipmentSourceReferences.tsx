import { ExternalLink } from 'lucide-react'

import type { EquipmentEntry } from '@/types/equipment'

interface EquipmentSourceReferencesProps {
  sources: EquipmentEntry['source_refs']
  calculationSource?: string
}

export function EquipmentSourceReferences({
  sources,
  calculationSource,
}: EquipmentSourceReferencesProps) {
  if (calculationSource !== undefined) {
    const url = new URL(calculationSource)
    if (url.protocol !== 'https:' || url.hostname !== 'metalmaniax.com') {
      throw new Error('载重加成补充出处地址无效')
    }
  }
  return (
    <section aria-labelledby="equipment-sources-heading">
      <h2
        id="equipment-sources-heading"
        className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        来源与定位
      </h2>

      {sources.length === 0 ? (
        <p className="border-border text-foreground mt-5 border-y py-5 text-sm">
          该记录没有可追溯来源
        </p>
      ) : (
        <ol className="border-border mt-5 border-t">
          {sources.map((source, index) => (
            <li
              key={`${source.source_id}:${source.target_id}:${source.table_index}:${source.row_index}:${index}`}
              className="border-border grid min-w-0 gap-3 border-b py-5 sm:grid-cols-[2rem_minmax(0,1fr)_auto] sm:gap-4"
            >
              <span className="font-mono text-xs font-semibold text-[var(--mm-navy)]">
                {String(index + 1).padStart(2, '0')}
              </span>

              <dl className="grid min-w-0 gap-x-5 gap-y-2 text-sm sm:grid-cols-2">
                <div className="min-w-0">
                  <dt className="font-medium text-[var(--mm-navy)]">
                    资料来源
                  </dt>
                  <dd className="text-foreground mt-0.5 font-mono text-xs break-all">
                    {source.source_id === 'metalmaniax-mm2r'
                      ? 'METAL MAniaX'
                      : source.source_id === 'zzjb-mm2r'
                        ? '重装机兵专题站'
                        : source.source_id}
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="font-medium text-[var(--mm-navy)]">
                    来源页面
                  </dt>
                  <dd className="text-foreground mt-0.5 font-mono text-xs break-all">
                    {source.target_id === 'maniax-sub-guns'
                      ? source.table_index > 0
                        ? '副炮总表'
                        : '副炮独立详情'
                      : source.target_id === 'maniax-special-equipment'
                        ? source.table_index > 0
                          ? 'S-E 总表'
                          : '装备独立详情'
                        : source.target_id === 'maniax-c-units'
                          ? decodeURIComponent(
                              new URL(source.source_url).search,
                            ).includes('検証')
                            ? '命中与回避验证'
                            : source.table_index === 0
                              ? '装备独立详情'
                              : 'C 装置与特性总表'
                          : source.target_id === 'maniax-engines'
                            ? source.table_index === 0
                              ? '引擎独立详情'
                              : '引擎与特性总表'
                            : source.target_id}
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="font-medium text-[var(--mm-navy)]">
                    表格编号
                  </dt>
                  <dd className="text-foreground mt-0.5">
                    {source.table_index + 1}
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="font-medium text-[var(--mm-navy)]">行号</dt>
                  <dd className="text-foreground mt-0.5">
                    {source.row_index + 1}
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="font-medium text-[var(--mm-navy)]">
                    采集日期
                  </dt>
                  <dd className="text-foreground mt-0.5 break-words">
                    <time dateTime={source.retrieved_at}>
                      {source.retrieved_at.slice(0, 10)}
                    </time>
                  </dd>
                </div>
              </dl>

              <a
                href={source.source_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`查看原始资料：${source.source_id}（在新窗口打开）`}
                className="focus-visible:ring-ring text-accent-foreground inline-flex min-h-10 max-w-full min-w-0 items-center gap-1.5 self-start text-sm font-medium underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none sm:justify-self-end"
              >
                <span className="break-words">查看原始资料</span>
                <ExternalLink
                  className="size-3.5 shrink-0"
                  aria-hidden="true"
                />
              </a>
            </li>
          ))}
        </ol>
      )}
      {calculationSource !== undefined && (
        <p className="text-muted-foreground mt-4 text-xs leading-6">
          加成计算另参考{' '}
          <a
            href={calculationSource}
            target="_blank"
            rel="noreferrer"
            className="focus-visible:ring-ring inline-flex min-h-10 items-center underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
          >
            METAL MAX 大辞典
          </a>
          。已核对其资料快照，原词典页面目前无法直接访问。
        </p>
      )}
    </section>
  )
}
