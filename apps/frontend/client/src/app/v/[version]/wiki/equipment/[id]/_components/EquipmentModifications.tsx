import type { EquipmentEntry } from '@/types/equipment'

const fields = [
  { label: '攻击力', initial: 'attack_raw', maximum: 'attack_max_raw' },
  { label: '防御力', initial: 'defense_raw', maximum: 'defense_max_raw' },
  { label: '弹仓', initial: 'magazine_raw', maximum: 'magazine_max_raw' },
  { label: '重量（t）', initial: 'weight_raw', maximum: 'weight_max_raw' },
] as const

function displayValue(value: string) {
  const text = value.replace(/t$/, '')
  return text === '' || text === '-' || text === '?' ? '—' : text
}

export function EquipmentModifications({ entry }: { entry: EquipmentEntry }) {
  const modifications = entry.modifications ?? []
  if (modifications.length === 0) return null
  const stars = entry.attributes.obtainable_stars_raw
  const obtainableStars =
    typeof stars === 'string' ? stars.split(',').map(Number) : []

  return (
    <section aria-labelledby="equipment-modifications-heading">
      <h2
        id="equipment-modifications-heading"
        className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        星级与改造
      </h2>
      <p className="text-muted-foreground mt-3 text-sm leading-6">
        下表为来源记录的普通改造范围，不含超改造。各项上限分别列出，重量上限不代表仅提高攻击力后的重量。
      </p>
      <div className="mt-6 grid min-w-0 gap-6 sm:grid-cols-2">
        {modifications.map((modification) => {
          const referenceOnly =
            obtainableStars.length > 0 &&
            !obtainableStars.includes(modification.stars)
          return (
            <div key={modification.stars} className="min-w-0">
              <h3 className="border-border flex flex-wrap items-baseline justify-between gap-2 border-b pb-3 text-sm font-semibold text-[var(--mm-navy)]">
                <span>
                  {modification.stars === 0
                    ? '无星'
                    : '★'.repeat(modification.stars)}
                </span>
                {obtainableStars.length > 0 && (
                  <span className="text-muted-foreground text-xs font-normal">
                    {referenceOnly ? '图鉴参考，获取未确认' : '来源记录可获取'}
                  </span>
                )}
              </h3>
              <table className="w-full table-fixed text-left text-sm">
                <caption className="sr-only">
                  {entry.name} {modification.stars} 星普通改造数值
                </caption>
                <thead className="text-muted-foreground text-xs">
                  <tr>
                    <th className="py-3 font-normal" scope="col">
                      项目
                    </th>
                    <th className="py-3 font-normal" scope="col">
                      初始
                    </th>
                    <th className="py-3 font-normal" scope="col">
                      改造上限
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((field) => (
                    <tr key={field.initial} className="border-border border-b">
                      <th className="py-3 pr-2 font-normal" scope="row">
                        {field.label}
                      </th>
                      <td className="py-3 pr-2 break-words">
                        {displayValue(modification[field.initial])}
                      </td>
                      <td className="py-3 break-words">
                        {displayValue(modification[field.maximum])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>
      <p className="text-muted-foreground mt-4 text-xs leading-6">
        — 表示来源未列出数值或该项不可改造；空缺数值未做推算。
      </p>
    </section>
  )
}
